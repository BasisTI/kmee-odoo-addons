# Copyright 2024 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from collections import defaultdict

from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from odoo.addons.l10n_br_hr_payroll.models.salary_rules_br import calc_ferias_dias

# Horizonte de uma ausência de férias: o fim do concessivo mais cinco anos, o
# prazo de prescrição (CLT art. 149; CF art. 7º, XXIX). Depois dele o período não
# recebe mais ausência.
L10N_BR_ANOS_PRESCRICAO = 5
# Validade vista pelo hr_holidays enquanto dura o cálculo do saldo: o concessivo
# (12 meses) e o horizonte, o mesmo deslocamento para todo período, para a ordem
# de expiração ficar igual à dos períodos (``_l10n_br_estender_concessivo``).
L10N_BR_VALIDADE = relativedelta(years=1 + L10N_BR_ANOS_PRESCRICAO)


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
        records._l10n_br_reconferir_notas()
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

    def _l10n_br_horizonte(self):
        """Último dia em que o período recebe ausência: o fim do concessivo mais
        cinco anos (prescrição, CLT art. 149)."""
        self.ensure_one()
        return self._l10n_br_fim_concessivo() + relativedelta(
            years=L10N_BR_ANOS_PRESCRICAO
        )

    def _l10n_br_reconferir_notas(self):
        """Alocação de Férias criada, validada, recusada, alterada ou excluída
        muda o débito das ausências do empregado: reconfere os avisos e notas."""
        vacation_type = self.env.ref(
            "l10n_br_hr_vacation.leave_type_ferias", raise_if_not_found=False
        )
        ferias = self.filtered(lambda alloc: alloc.holiday_status_id == vacation_type)
        if ferias:
            self.env["hr.leave"]._l10n_br_atualizar_notas(ferias.employee_id)

    def unlink(self):
        employees = self.filtered(
            lambda alloc: alloc.holiday_status_id
            == self.env.ref("l10n_br_hr_vacation.leave_type_ferias", False)
        ).employee_id
        res = super().unlink()
        self.env["hr.leave"]._l10n_br_atualizar_notas(employees)
        return res

    def write(self, vals):
        sai_de_validada = "state" in vals and vals["state"] != "validate"
        if ({"number_of_days"} & set(vals) or sai_de_validada) and not {
            "date_from",
            "date_to",
            "l10n_br_faltas_periodo_aquisitivo",
        } & set(vals):
            self.filtered(
                lambda a: a.state == "validate"
            )._l10n_br_recusar_se_usada_em_rescisao(vals)
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
            self._l10n_br_recusar_se_usada_em_rescisao(vals)
        res = super().write(vals)
        if {"state", "date_from", "date_to", "l10n_br_faltas_periodo_aquisitivo"} & set(
            vals
        ):
            self._l10n_br_reconferir_notas()
        return res

    def _l10n_br_recusar_se_usada_em_rescisao(self, vals):
        """TG-147: o período que uma rescisão confirmada pagou (vencido ou o que
        se completa na projeção do aviso, ``date_to`` <= data projetada) não muda
        de datas, de faltas, de dias nem de estado (recusar, voltar a rascunho)
        enquanto ela estiver confirmada; rescisão aberta apenas recalcula."""
        vacation_type = self.env.ref(
            "l10n_br_hr_vacation.leave_type_ferias", raise_if_not_found=False
        )
        for alloc in self.filtered(lambda a: a.holiday_status_id == vacation_type):
            datas = [alloc.date_to]
            if vals.get("date_to"):
                datas.append(fields.Date.to_date(vals["date_to"]))
            rescisoes = (
                self.env["hr.payslip"]
                .sudo()
                .search(
                    [
                        ("employee_id", "=", alloc.employee_id.id),
                        ("struct_id.code", "=", "RESCISAO"),
                        ("state", "=", "done"),
                        ("l10n_br_fora_de_vigor", "=", False),
                    ]
                )
            )
            usadas = rescisoes.filtered(
                lambda r: any(
                    d and d <= r._l10n_br_data_projetada_rescisao() for d in datas
                )
            )
            if usadas:
                raise UserError(
                    _(
                        "O período aquisitivo foi pago pela rescisão confirmada "
                        "%(rescisoes)s (férias vencidas ou do período que se "
                        "completa no aviso prévio indenizado): as datas, as "
                        "faltas, os dias e o estado definem o valor pago. Volte a rescisão "
                        "para rascunho antes de alterá-las.",
                        rescisoes=", ".join(
                            usadas.mapped(lambda r: r.number or r.name)
                        ),
                    )
                )

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
    def _l10n_br_periodo_do_recibo(self, employee, datas):
        """``{início: id da alocação}`` dos recibos de férias (rascunho ou
        confirmado, não cancelado) do empregado que começam nessas datas: o
        recibo fixa o período que a ausência debita (escolha explícita)."""
        recibos = (
            self.env["hr.payslip"]
            .sudo()
            .search(
                [
                    ("employee_id", "=", employee.id),
                    ("struct_id.code", "=", "FERIAS"),
                    ("state", "!=", "cancel"),
                    ("l10n_br_ferias_allocation_id", "!=", False),
                    ("date_from", "in", list(datas)),
                ],
                order="id",
            )
        )
        return {rec.date_from: rec.l10n_br_ferias_allocation_id.id for rec in recibos}

    @api.model
    def _l10n_br_ausencias_ferias(self, employee, antes=None, excluir=()):
        """Ausências de férias ativas do empregado em dias corridos.

        Returns:
            list[tuple]: ``(id, início, fim, período do recibo)`` por data de
            início; o último é o id da alocação do recibo de férias que começa no
            mesmo dia (a ausência já paga debita o período do recibo, que é a
            escolha explícita) ou 0. ``antes=(data, id)`` fica só com as que
            começam antes desse ponto.
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
        do_recibo = self._l10n_br_periodo_do_recibo(
            employee, leaves.mapped("request_date_from")
        )
        itens = [
            (
                lv.id,
                lv.request_date_from,
                lv.request_date_to,
                do_recibo.get(lv.request_date_from, 0),
            )
            for lv in leaves
        ]
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
    def _l10n_br_destino(self, alocacoes, restante, data, horizontes=None):
        """Período que uma ausência começando em ``data`` debita: o mais antigo,
        de aquisitivo já completo (CLT art. 134), com saldo real em dias
        corridos. Primeiro o vencido (concessivo expirado, em dobro, art. 137);
        sem vencido com saldo, o que ainda está no concessivo. Vazio se nenhum."""
        horizontes = horizontes or {a: a._l10n_br_horizonte() for a in alocacoes}
        for alloc in alocacoes:
            if (
                alloc.date_to < data
                and restante[alloc] > 0
                and horizontes[alloc] >= data
            ):
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
        horizontes = {
            a: a._l10n_br_horizonte() for a in alocacoes
        }  # uma vez por período
        destino, excesso, saldo_antes = {}, {}, {}
        for chave, inicio, fim, *do_recibo in ausencias:
            dias = (fim - inicio).days + 1
            # o recibo fixa o período só se ele está completo no início e dentro do
            # horizonte (a mesma regra da ausência)
            alloc = alocacoes.filtered(
                lambda a: do_recibo
                and a.id == do_recibo[0]
                and a.date_to < inicio
                and horizontes[a] >= inicio
            )
            alloc = alloc or self._l10n_br_destino(
                alocacoes, restante, inicio, horizontes
            )
            destino[chave] = alloc
            saldo_antes[chave] = restante[alloc] if alloc else 0
            usa = min(dias, max(restante[alloc], 0)) if alloc else 0
            if alloc:
                restante[alloc] -= usa
            excesso[chave] = dias - usa
        return restante, destino, excesso, saldo_antes

    @api.model
    def _l10n_br_analise(self, employee, extra=(), excluir=()):
        """Fonte única do período debitado por cada ausência de férias.

        O aviso de dobra, a nota, os dias em dobro, a restrição de saldo e o
        seletor leem daqui. ``extra`` são ausências ainda não gravadas
        (``(chave, início, fim)``), que entram na ordem das datas; o período do
        recibo de férias que começa no mesmo dia fixa o débito.

        Returns:
            dict: ``{chave: (período debitado, dias em excesso, saldo antes)}``.
        """
        alocacoes = self._l10n_br_alocacoes_ferias(employee)
        ausencias = self._l10n_br_ausencias_ferias(employee, excluir=excluir)
        extras = list(extra)
        if extras:
            do_recibo = self._l10n_br_periodo_do_recibo(
                employee, [t[1] for t in extras]
            )
            ausencias += [(c, i, f, do_recibo.get(i, 0)) for c, i, f in extras]
            ausencias.sort(key=lambda t: (t[1], t[0]))
        _restante, destino, excesso, saldo = self._l10n_br_distribuir(
            alocacoes, ausencias
        )
        return {c: (destino[c], excesso[c], saldo[c]) for c in destino}

    @api.model
    def _l10n_br_outro_periodo_com_saldo(self, employee, alloc, data, excluir=()):
        """Há outro período, completo em ``data`` e dentro do horizonte, com saldo?"""
        alocacoes = self._l10n_br_alocacoes_ferias(employee)
        ausencias = self._l10n_br_ausencias_ferias(employee, excluir=excluir)
        restante = self._l10n_br_distribuir(alocacoes, ausencias)[0]
        return any(
            a != alloc
            and a.date_to < data
            and a._l10n_br_horizonte() >= data
            and restante[a] > 0
            for a in alocacoes
        )

    @api.model
    def _l10n_br_periodo_com_saldo(self, employee, data):
        """Período que uma ausência de um dia em ``data`` debitaria (vazio se
        nenhum tem saldo): o seletor do tipo Férias."""
        analise = self._l10n_br_analise(employee, extra=[(-1, data, data)])
        return analise[-1][0] if analise.get(-1) else self.browse()

    @api.model
    def _l10n_br_estender_concessivo(self, employees, target_date=None):
        """Faz o ``hr_holidays`` ver as alocações de férias válidas até o fim do
        concessivo mais cinco anos, sem gravar nada.

        ``date_to`` é o fim do período aquisitivo e continua sendo (dobra,
        férias vencidas e recibo o leem). O ``hr_holidays`` o usa como fim da
        validade do saldo, em vários pontos (consumo, saldo exibido, seletor
        do tipo de folga). Enquanto dura o cálculo do saldo, o valor em cache
        de ``date_to`` fica 6 anos à frente (12 meses de concessivo, CLT art.
        134, e 5 de horizonte, o prazo de prescrição do art. 149) em TODO período
        de Férias, o mesmo deslocamento para todos: a ordem de expiração do
        ``hr_holidays`` (e, com ela, a do consumo) fica igual à dos períodos, e
        o horizonte é curto (sem o custo de calendário de uma validade de
        décadas). Quem aceita ou recusa a ausência é a restrição em dias
        corridos (``_l10n_br_distribuir``), uma fonte só: período em curso é
        recusado (art. 134) e período depois do horizonte também.
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
        originais = {alloc: alloc.date_to for alloc in alocacoes}
        field = self._fields["date_to"]
        for alloc, date_to in originais.items():
            self.env.cache.set(alloc, field, date_to + L10N_BR_VALIDADE)
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
