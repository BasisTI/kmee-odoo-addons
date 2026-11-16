# Copyright 2026 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import api, fields, models


class HrLeaveType(models.Model):
    _inherit = "hr.leave.type"

    def get_allocation_data(self, employees, *args, **kwargs):
        """Saldo exibido e validação da ausência até o fim do concessivo."""
        Allocation = self.env["hr.leave.allocation"]
        # o 1º argumento posicional depois dos empregados é a data da ausência
        data = args[0] if args else kwargs.get("target_date")
        originais = Allocation._l10n_br_estender_concessivo(employees, data)
        try:
            return super().get_allocation_data(employees, *args, **kwargs)
        finally:
            Allocation._l10n_br_restaurar_concessivo(originais)

    def _l10n_br_ferias(self):
        vacation_type = self.env.ref(
            "l10n_br_hr_vacation.leave_type_ferias", raise_if_not_found=False
        )
        return self.filtered(lambda lt: vacation_type and lt == vacation_type)

    @api.depends("requires_allocation", "max_leaves", "virtual_remaining_leaves")
    def _compute_valid(self):
        """O seletor do tipo de folga também enxerga o concessivo e, com saldo
        real em dias corridos, o período vencido (férias em dobro)."""
        res = super()._compute_valid()
        employee_id = self._context.get(
            "default_employee_id",
            self._context.get("employee_id", self.env.user.employee_id.id),
        )
        employee = self.env["hr.employee"].browse(employee_id)
        date_from = self._l10n_br_data(
            self._context.get("default_date_from", fields.Datetime.today())
        )
        for leave_type in self._l10n_br_ferias():
            if (
                leave_type.has_valid_allocation
                or leave_type.requires_allocation != "yes"
            ):
                continue
            leave_type.has_valid_allocation = bool(
                self.env["hr.leave.allocation"]._l10n_br_periodo_debitado(
                    employee, date_from, com_saldo=True
                )
            )
        return res

    @api.model
    def _search_valid(self, operator, value):
        domain = super()._search_valid(operator, value)
        vacation_type = self.env.ref(
            "l10n_br_hr_vacation.leave_type_ferias", raise_if_not_found=False
        )
        if not vacation_type:
            return domain
        if {"default_date_from", "tz"} <= set(self._context):
            data = fields.Date.context_today(
                self, fields.Datetime.to_datetime(self._context["default_date_from"])
            )
        else:
            data = fields.Date.today()
        employee_id = (
            self._context.get("default_employee_id", self._context.get("employee_id"))
            or self.env.user.employee_id.id
        )
        employee = self.env["hr.employee"].browse(employee_id)
        com_saldo = bool(
            self.env["hr.leave.allocation"]._l10n_br_periodo_debitado(
                employee, data, com_saldo=True
            )
        )
        _campo, operador, ids = domain[0]
        ids = set(ids)
        # Férias é válido para o seletor só com dias corridos de direito (o saldo
        # em dias úteis do hr_holidays não decide): entra no conjunto dos válidos
        # com saldo e sai dele sem saldo.
        if (operador == "in") == com_saldo:
            ids.add(vacation_type.id)
        else:
            ids.discard(vacation_type.id)
        return [("id", operador, list(ids))]

    @staticmethod
    def _l10n_br_data(valor):
        return fields.Datetime.to_datetime(valor).date()
