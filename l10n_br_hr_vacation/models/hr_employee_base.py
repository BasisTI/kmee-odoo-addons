# Copyright 2026 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import models


class HrEmployeeBase(models.AbstractModel):
    _inherit = "hr.employee.base"

    def _get_consumed_leaves(self, leave_types, target_date=False, ignore_future=False):
        """Saldo e consumo das férias valem até o fim do período concessivo
        (CLT art. 134): ver ``hr.leave.allocation._l10n_br_estender_concessivo``.
        Alimenta a validação da ausência, o saldo do tipo de folga e os "dias
        tomados" da alocação, sempre pela mesma regra."""
        employees = self or self._get_contextual_employee()
        Allocation = self.env["hr.leave.allocation"]
        originais = Allocation._l10n_br_estender_concessivo(employees)
        try:
            return super()._get_consumed_leaves(
                leave_types, target_date=target_date, ignore_future=ignore_future
            )
        finally:
            Allocation._l10n_br_restaurar_concessivo(originais)
