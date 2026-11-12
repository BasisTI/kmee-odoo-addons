# Copyright 2024 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import api, models


class HrLeave(models.Model):
    _inherit = "hr.leave"

    # Afastamento previdenciário validado, recusado ou alterado depois do
    # holerite muda quais faltas valem (o dia afastado não gera falta) e, com
    # isso, o DSR que cada holerite do empregado desconta. Entra no mesmo ponto
    # único antes/depois do ``hr.payslip``: recalcula o dependente aberto e
    # recusa o fechado.
    _L10N_BR_CAMPOS_DSR = (
        "state",
        "employee_id",
        "holiday_status_id",
        "date_from",
        "date_to",
        "request_date_from",
        "request_date_to",
    )

    def _l10n_br_com_reconciliacao_dsr(self, operacao, empregados):
        Payslip = self.env["hr.payslip"]
        if self.env.context.get("l10n_br_dsr_reconciliando"):
            return operacao()
        empregados |= self.employee_id
        antes = Payslip._l10n_br_dsr_participacao(empregados)
        res = operacao()
        Payslip._l10n_br_dsr_reconciliar(
            antes, empregados | self.exists().employee_id, Payslip.browse()
        )
        return res

    @api.model_create_multi
    def create(self, vals_list):
        empregados = self.env["hr.employee"].browse(
            [v["employee_id"] for v in vals_list if v.get("employee_id")]
        )
        Payslip = self.env["hr.payslip"]
        if self.env.context.get("l10n_br_dsr_reconciliando"):
            return super().create(vals_list)
        antes = Payslip._l10n_br_dsr_participacao(empregados)
        leaves = super().create(vals_list)
        Payslip._l10n_br_dsr_reconciliar(
            antes, empregados | leaves.employee_id, Payslip.browse()
        )
        return leaves

    def write(self, vals):
        if not self or not set(vals) & set(self._L10N_BR_CAMPOS_DSR):
            return super().write(vals)
        empregados = self.env["hr.employee"].browse(
            [vals["employee_id"]] if vals.get("employee_id") else []
        )
        return self._l10n_br_com_reconciliacao_dsr(
            lambda: super(HrLeave, self).write(vals), empregados
        )

    def unlink(self):
        empregados = self.employee_id
        return self._l10n_br_com_reconciliacao_dsr(
            lambda: super(HrLeave, self).unlink(), empregados
        )
