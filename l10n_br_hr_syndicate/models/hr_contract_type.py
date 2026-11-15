# Copyright 2024 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import fields, models


class HrContractType(models.Model):
    _inherit = "hr.contract.type"

    l10n_br_prazo_determinado = fields.Boolean(
        string="Prazo Determinado",
        help="Contrato por prazo determinado: não conta como período de "
        "experiência para a isenção da contribuição assistencial (617) da CCT, "
        "mesmo com as datas de experiência preenchidas.",
    )

    def write(self, vals):
        if "l10n_br_prazo_determinado" not in vals:
            return super().write(vals)
        contratos = (
            self.env["hr.contract"]
            .sudo()
            .search([("contract_type_id", "in", self.ids)])
        )
        return self.env["hr.payslip"]._l10n_br_contribuicao_guardar(
            contratos._l10n_br_holerites_cct(),
            lambda: super(HrContractType, self).write(vals),
        )
