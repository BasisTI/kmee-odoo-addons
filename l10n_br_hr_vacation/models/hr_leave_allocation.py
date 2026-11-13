# Copyright 2024 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from dateutil.relativedelta import relativedelta

from odoo import api, fields, models

from odoo.addons.l10n_br_hr_payroll.models.salary_rules_br import calc_ferias_dias


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

    @api.model
    def _l10n_br_estender_concessivo(self, employees):
        """Faz o ``hr_holidays`` ver as alocações de férias válidas até o fim
        do período concessivo (CLT art. 134), sem gravar nada.

        ``date_to`` é o fim do período aquisitivo e continua sendo (dobra,
        férias vencidas e recibo o leem). O ``hr_holidays`` o usa como fim da
        validade do saldo, em vários pontos (consumo, saldo exibido, seletor
        do tipo de folga). Enquanto dura o cálculo do saldo, o valor em cache
        de ``date_to`` fica 12 meses à frente; ``_l10n_br_restaurar_concessivo``
        devolve o original. Reentrante: só a chamada mais externa troca.

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
            self.env.cache.set(alloc, field, date_to + relativedelta(years=1))
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
