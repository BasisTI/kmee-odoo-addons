# Copyright 2026 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from dateutil.relativedelta import relativedelta

from odoo import api, fields, models


class HrLeaveType(models.Model):
    _inherit = "hr.leave.type"

    def get_allocation_data(self, employees, *args, **kwargs):
        """Saldo exibido e validação da ausência até o fim do concessivo."""
        Allocation = self.env["hr.leave.allocation"]
        originais = Allocation._l10n_br_estender_concessivo(employees)
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
        """O seletor do tipo de folga também enxerga o concessivo."""
        res = super()._compute_valid()
        employee_id = self._context.get(
            "default_employee_id",
            self._context.get("employee_id", self.env.user.employee_id.id),
        )
        date_from = self._l10n_br_data(
            self._context.get("default_date_from", fields.Datetime.today())
        )
        date_to = self._l10n_br_data(
            self._context.get("default_date_to", fields.Datetime.today())
        )
        for leave_type in self._l10n_br_ferias():
            if (
                leave_type.has_valid_allocation
                or leave_type.requires_allocation != "yes"
            ):
                continue
            alocacoes = self.env["hr.leave.allocation"].search(
                [
                    ("holiday_status_id", "=", leave_type.id),
                    ("employee_id", "=", employee_id),
                    ("date_from", "<=", date_from),
                    ("date_to", "!=", False),
                ]
            )
            alocacoes = alocacoes.filtered(
                lambda alloc: alloc.date_to + relativedelta(years=1) >= date_to
                and alloc.max_leaves > 0
                and alloc.max_leaves - alloc.leaves_taken > 0
            )
            leave_type.has_valid_allocation = bool(alocacoes)
        return res

    @api.model
    def _search_valid(self, operator, value):
        domain = super()._search_valid(operator, value)
        vacation_type = self.env.ref(
            "l10n_br_hr_vacation.leave_type_ferias", raise_if_not_found=False
        )
        if not vacation_type:
            return domain
        if {"default_date_from", "default_date_to", "tz"} <= set(self._context):
            date_from = fields.Date.context_today(
                self, fields.Datetime.to_datetime(self._context["default_date_from"])
            )
            date_to = fields.Date.context_today(
                self, fields.Datetime.to_datetime(self._context["default_date_to"])
            )
        else:
            date_from = fields.Date.today().replace(month=1, day=1)
            date_to = fields.Date.today().replace(month=12, day=31)
        employee_id = (
            self._context.get("default_employee_id", self._context.get("employee_id"))
            or self.env.user.employee_id.id
        )
        no_concessivo = bool(
            self.env["hr.leave.allocation"].search_count(
                [
                    ("employee_id", "=", employee_id),
                    ("holiday_status_id", "=", vacation_type.id),
                    ("state", "=", "validate"),
                    ("date_from", "<=", date_to),
                    ("date_to", "!=", False),
                    ("date_to", ">=", date_from - relativedelta(years=1)),
                ]
            )
        )
        if not no_concessivo:
            return domain
        _campo, operador, ids = domain[0]
        ids = set(ids)
        if operador == "in":
            ids.add(vacation_type.id)
        else:
            ids.discard(vacation_type.id)
        return [("id", operador, list(ids))]

    @staticmethod
    def _l10n_br_data(valor):
        return fields.Datetime.to_datetime(valor).date()
