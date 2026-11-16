# Copyright 2024 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from collections import defaultdict

from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from odoo.addons.l10n_br_hr_payroll.models.salary_rules_br import calc_ferias_dias

# Validade vista pelo hr_holidays, enquanto dura o cálculo do saldo, no período
# debitado pela ausência (ver ``_l10n_br_estender_concessivo``): sem fim prático.
L10N_BR_SEM_LIMITE = relativedelta(years=100)


class HrLeaveAllocation(models.Model):
    _inherit = "hr.leave.allocation"

    l10n_br_faltas_periodo_aquisitivo = fields.Integer(
        string="Faltas no Período Aquisitivo",
        default=0,
        help="Faltas injustificadas no período aquisitivo (CLT art. 130)",
    )

    @api.model_create_multi
    def create(self, vals_list):
        """RF-19 (bug latente corrigido): força o recômputo dos dias de
        direito em alocações de férias criadas SEM passar por um write()
        posterior a ``l10n_br_faltas_periodo_aquisitivo``.

        ``number_of_days`` é um campo computado (``_compute_number_of_days``)
        mas com ``default=1`` do próprio hr_holidays.
        No ``create()``, o Odoo preenche esse default ANTES do compute
        (``_add_missing_default_values``) e PROTEGE o valor já presente em
        vals contra recômputo (``env.protecting``) - então uma alocação
        criada só com ``holiday_status_id``/datas (sem tocar em
        ``l10n_br_faltas_periodo_aquisitivo`` à parte) ficava travada em 1
        dia, em vez dos 30/24/18/12 dias de direito (CLT art. 130). Um
        ``write()`` já disparava o recômputo (a proteção só existe durante o
        ``create()``); o gatilho aqui faz o ``create()`` direto ter o mesmo
        resultado.
        """
        records = super().create(vals_list)
        vacation_type = self.env.ref(
            "l10n_br_hr_vacation.leave_type_ferias", raise_if_not_found=False
        )
        if vacation_type:
            a_recomputar = records.filtered(
                lambda alloc: alloc.holiday_status_id == vacation_type
            )
            if a_recomputar:
                a_recomputar._compute_number_of_days()
        return records

    @api.depends("l10n_br_faltas_periodo_aquisitivo")
    def _compute_number_of_days(self):
        """Extend to compute vacation days based on absences (CLT art. 130)."""
        super()._compute_number_of_days()
        vacation_type = self.env.ref(
            "l10n_br_hr_vacation.leave_type_ferias", raise_if_not_found=False
        )
        if not vacation_type:
            return
        for alloc in self:
            if alloc.holiday_status_id == vacation_type:
                dias = calc_ferias_dias(alloc.l10n_br_faltas_periodo_aquisitivo)
                # SQL constraint requires number_of_days > 0 for regular allocs.
                # When employee loses vacation right (33+ faltas), we keep 1 day
                # to satisfy the constraint; the field value signals the loss.
                alloc.number_of_days = max(dias, 1) if dias == 0 else dias

    def _l10n_br_fim_concessivo(self):
        """Último dia do período concessivo: 12 meses após o fim do aquisitivo
        (CLT art. 134). Férias gozadas depois dele são pagas em dobro."""
        self.ensure_one()
        return self.date_to and self.date_to + relativedelta(years=1)

    def write(self, vals):
        if {"date_from", "date_to", "l10n_br_faltas_periodo_aquisitivo"} & set(vals):
            confirmados = (
                self.env["hr.payslip"]
                .sudo()
                .search_count(
                    [
                        ("l10n_br_ferias_allocation_id", "in", self.ids),
                        ("state", "=", "done"),
                        ("l10n_br_fora_de_vigor", "=", False),
                    ]
                )
            )
            if confirmados:
                raise UserError(
                    _(
                        "O período aquisitivo tem recibo de férias confirmado: a "
                        "dobra (CLT art. 137) e os dias de direito e pagos dependem "
                        "das datas e das faltas. Volte o recibo para rascunho antes "
                        "de alterá-las."
                    )
                )
        return super().write(vals)

    # -- período debitado pela ausência de férias (CLT arts. 134 e 137) ---------
    #
    # O tipo Férias conta dias úteis no ``hr_holidays``: 30 dias corridos gastam
    # ~22 e o abono nem vira ausência, então a sobra do saldo em dias úteis não é
    # saldo de férias. Por isso o período que uma ausência debita é decidido aqui,
    # em dias corridos: o período de aquisitivo completo mais antigo com saldo
    # real, o vencido primeiro (férias em dobro) e depois o do concessivo.

    @api.model
    def _l10n_br_alocacoes_ferias(self, employee):
        vacation_type = self.env.ref(
            "l10n_br_hr_vacation.leave_type_ferias", raise_if_not_found=False
        )
        if not vacation_type or not employee:
            return self.browse()
        return (
            self.sudo()
            .with_context(active_test=False)
            .search(
                [
                    ("employee_id", "=", employee.id),
                    ("holiday_status_id", "=", vacation_type.id),
                    ("state", "=", "validate"),
                    ("date_to", "!=", False),
                ],
                order="date_to, id",
            )
        )

    @api.model
    def _l10n_br_ausencias_ferias(self, employee, antes=None, excluir=()):
        """Ausências de férias ativas do empregado em dias corridos.

        Returns:
            list[tuple]: ``(id, início, fim)`` por data de início.
            ``antes=(data, id)`` fica só com as que começam antes desse ponto.
        """
        vacation_type = self.env.ref(
            "l10n_br_hr_vacation.leave_type_ferias", raise_if_not_found=False
        )
        if not vacation_type or not employee:
            return []
        leaves = (
            self.env["hr.leave"]
            .sudo()
            .search(
                [
                    ("employee_id", "=", employee.id),
                    ("holiday_status_id", "=", vacation_type.id),
                    ("state", "in", ("confirm", "validate1", "validate")),
                    ("request_date_from", "!=", False),
                    ("request_date_to", "!=", False),
                    ("id", "not in", list(excluir)),
                ]
            )
        )
        itens = sorted(
            (lv.id, lv.request_date_from, lv.request_date_to) for lv in leaves
        )
        itens.sort(key=lambda t: (t[1], t[0]))
        if antes:
            itens = [t for t in itens if (t[1], t[0]) < antes]
        return itens

    @api.model
    def _l10n_br_saldo_corridos(self, alocacoes):
        """Dias de direito de cada período, menos o abono já lançado em recibo."""
        abono = defaultdict(int)
        recibos = (
            self.env["hr.payslip"]
            .sudo()
            .search(
                [
                    ("l10n_br_ferias_allocation_id", "in", alocacoes.ids),
                    ("state", "!=", "cancel"),
                ]
            )
        )
        for recibo in recibos:
            abono[recibo.l10n_br_ferias_allocation_id.id] += recibo.l10n_br_dias_abono
        return {alloc: alloc.number_of_days - abono[alloc.id] for alloc in alocacoes}

    @api.model
    def _l10n_br_destino(self, alocacoes, restante, data):
        """Período que uma ausência começando em ``data`` debita: o mais antigo,
        de aquisitivo já completo (CLT art. 134), com saldo real em dias
        corridos. Primeiro o vencido (concessivo expirado, em dobro, art. 137);
        sem vencido com saldo, o que ainda está no concessivo. Vazio se nenhum."""
        for alloc in alocacoes:
            if alloc.date_to < data and restante[alloc] > 0:
                return alloc
        return alocacoes.browse()

    @api.model
    def _l10n_br_distribuir(self, alocacoes, ausencias):
        """Debita, em ordem e em dias corridos, cada ausência num ÚNICO período.

        Sem transbordo: o que passa do saldo do período fica como excesso (a
        ausência é recusada; o resto vai em outra ausência). Cada período só
        debita o que tem; o dado legado acima do direito não vai abaixo de zero.
        Férias coletivas (CLT art. 140) ficam fora desse limite.

        Returns:
            tuple: ``(restante, destino, excesso, saldo_antes)``: dias que sobram
            por período; período de cada ausência (``{id: alocação}``, vazio se
            nenhum tem saldo); dias sem saldo (``{id: dias}``); saldo do período
            antes da ausência (``{id: dias}``).
        """
        restante = self._l10n_br_saldo_corridos(alocacoes)
        destino, excesso, saldo_antes = {}, {}, {}
        for chave, inicio, fim in ausencias:
            dias = (fim - inicio).days + 1
            alloc = self._l10n_br_destino(alocacoes, restante, inicio)
            destino[chave] = alloc
            saldo_antes[chave] = restante[alloc] if alloc else 0
            usa = min(dias, max(restante[alloc], 0)) if alloc else 0
            if alloc:
                restante[alloc] -= usa
            excesso[chave] = dias - usa
        return restante, destino, excesso, saldo_antes

    @api.model
    def _l10n_br_periodo_debitado(self, employee, data, antes=None):
        """Período que uma ausência de férias começando em ``data`` debita
        (vazio se nenhum com saldo), contando só as ausências anteriores a
        ``antes``."""
        alocacoes = self._l10n_br_alocacoes_ferias(employee)
        if not alocacoes:
            return alocacoes
        ausencias = self._l10n_br_ausencias_ferias(employee, antes=antes or (data, 0))
        restante = self._l10n_br_distribuir(alocacoes, ausencias)[0]
        return self._l10n_br_destino(alocacoes, restante, data)

    @api.model
    def _l10n_br_estender_concessivo(self, employees, target_date=None):
        """Faz o ``hr_holidays`` ver as alocações de férias válidas até o fim
        do período concessivo (CLT art. 134), sem gravar nada, e o período
        debitado pela ausência de ``target_date`` sem limite de validade.

        ``date_to`` é o fim do período aquisitivo e continua sendo (dobra,
        férias vencidas e recibo o leem). O ``hr_holidays`` o usa como fim da
        validade do saldo, em vários pontos (consumo, saldo exibido, seletor
        do tipo de folga). Enquanto dura o cálculo do saldo, o valor em cache
        de ``date_to`` fica 12 meses à frente; só o período que a ausência
        debita (``_l10n_br_periodo_debitado``) fica sem teto, para as férias
        depois do concessivo serem aceitas e pagas em dobro (CLT art. 137). Os
        demais períodos não absorvem a ausência com a sobra de dias úteis.
        Sem ``target_date`` (saldo exibido), todos ficam no concessivo.
        ``_l10n_br_restaurar_concessivo`` devolve o original. Reentrante: só a
        chamada mais externa troca.

        Returns:
            dict | None: ``{alocação: date_to original}`` a restaurar, ou
            ``None`` quando nada foi trocado (já estendido por quem chamou).
        """
        cache_cr = self.env.cr.cache
        if cache_cr.get("l10n_br_concessivo") is not None:
            return None
        vacation_type = self.env.ref(
            "l10n_br_hr_vacation.leave_type_ferias", raise_if_not_found=False
        )
        if not vacation_type or not employees:
            return None
        alocacoes = (
            self.sudo()
            .with_context(active_test=False)
            .search(
                [
                    ("employee_id", "in", employees.ids),
                    ("holiday_status_id", "=", vacation_type.id),
                    ("state", "=", "validate"),
                    ("date_to", "!=", False),
                ]
            )
        )
        data = fields.Date.to_date(target_date) if target_date else None
        debitados = self.browse()
        if data:
            for employee in employees:
                debitados |= self._l10n_br_periodo_debitado(employee, data)
        originais = {alloc: alloc.date_to for alloc in alocacoes}
        field = self._fields["date_to"]
        for alloc, date_to in originais.items():
            ate = L10N_BR_SEM_LIMITE if alloc in debitados else relativedelta(years=1)
            self.env.cache.set(alloc, field, date_to + ate)
        cache_cr["l10n_br_concessivo"] = originais
        return originais

    @api.model
    def _l10n_br_restaurar_concessivo(self, originais):
        if originais is None:
            return
        field = self._fields["date_to"]
        for alloc, date_to in originais.items():
            self.env.cache.set(alloc, field, date_to)
        self.env.cr.cache.pop("l10n_br_concessivo", None)
