# Copyright 2026 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from datetime import timedelta

from odoo import _, api, fields, models


class HrLeave(models.Model):
    _inherit = "hr.leave"

    l10n_br_aviso_dobro = fields.Char(
        string="Aviso de Férias em Dobro",
        compute="_compute_l10n_br_aviso_dobro",
        help="Férias concedidas depois do período concessivo (CLT art. 134) são "
        "pagas em dobro, com o terço (CLT art. 137); nos dias que cruzam o fim do "
        "concessivo, só os dias depois dele (Súmula 81 do TST).",
    )

    def _l10n_br_dias_dobro(self):
        """Dias corridos da ausência depois do concessivo do período aquisitivo
        mais antigo com saldo (o que o ``hr_holidays`` consome primeiro).

        Returns:
            tuple[int, date | None]: dias em dobro e o fim do concessivo.
        """
        self.ensure_one()
        vacation_type = self.env.ref(
            "l10n_br_hr_vacation.leave_type_ferias", raise_if_not_found=False
        )
        inicio = self.request_date_from
        fim = self.request_date_to
        if (
            not vacation_type
            or self.holiday_status_id != vacation_type
            or not self.employee_id
            or not inicio
            or not fim
        ):
            return 0, None
        alocacoes = (
            self.env["hr.leave.allocation"]
            .sudo()
            .search(
                [
                    ("employee_id", "=", self.employee_id.id),
                    ("holiday_status_id", "=", vacation_type.id),
                    ("state", "=", "validate"),
                    ("date_from", "<=", fim),
                    ("date_to", "!=", False),
                ],
                order="date_to, id",
            )
        )
        # a ausência já consumida (validada) volta ao saldo para achar o período
        # de onde ela saiu
        devolvido = (
            self.number_of_days
            if self.id and self.state in ("confirm", "validate1", "validate")
            else 0
        )
        for alloc in alocacoes:
            if alloc.max_leaves - alloc.leaves_taken + devolvido > 0:
                limite = alloc._l10n_br_fim_concessivo()
                depois = max(inicio, limite + timedelta(days=1))
                return max((fim - depois).days + 1, 0), limite
        return 0, None

    @api.depends(
        "holiday_status_id", "employee_id", "request_date_from", "request_date_to"
    )
    def _compute_l10n_br_aviso_dobro(self):
        for leave in self:
            dias, limite = leave._l10n_br_dias_dobro()
            leave.l10n_br_aviso_dobro = (
                _(
                    "Atenção RH: %(dias)s dia(s) depois do fim do período concessivo "
                    "(%(limite)s). Esses dias são pagos em dobro, com o terço "
                    "(CLT art. 137).",
                    dias=dias,
                    limite=fields.Date.to_string(limite),
                )
                if dias
                else False
            )

    @api.onchange(
        "holiday_status_id", "employee_id", "request_date_from", "request_date_to"
    )
    def _onchange_l10n_br_aviso_dobro(self):
        self._compute_l10n_br_aviso_dobro()
        if self.l10n_br_aviso_dobro:
            return {
                "warning": {
                    "title": _("Férias em dobro"),
                    "message": self.l10n_br_aviso_dobro,
                }
            }

    @api.model_create_multi
    def create(self, vals_list):
        leaves = super().create(vals_list)
        for leave in leaves:
            aviso = leave._l10n_br_dias_dobro()[0] and leave.l10n_br_aviso_dobro
            if aviso:
                leave.message_post(body=aviso, subtype_xmlid="mail.mt_note")
        return leaves
