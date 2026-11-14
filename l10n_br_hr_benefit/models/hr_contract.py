# Copyright 2026 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import fields, models


class HrContract(models.Model):
    _inherit = "hr.contract"

    l10n_br_vavr_dispensado = fields.Boolean(
        string="VA/VR dispensado de desconto",
        help="Marcado, o empregado não sofre o desconto de VA/VR (rubrica 071) "
        "neste contrato: o desconto é 0,00 e não cai para as faixas da CCT.",
        tracking=True,
    )

    def _l10n_br_vavr_holerites(self):
        """Holerites vivos destes contratos cuja estrutura calcula o desconto 071."""
        holerites = (
            self.env["hr.payslip"]
            .sudo()
            .search([("contract_id", "in", self.ids), ("state", "!=", "cancel")])
        )
        return holerites.filtered(
            lambda r: "DESC_VAVR" in r._get_salary_rules().mapped("code")
        )

    def write(self, vals):
        if "l10n_br_vavr_dispensado" not in vals:
            return super().write(vals)
        mudam = self.filtered(
            lambda c: c.l10n_br_vavr_dispensado != bool(vals["l10n_br_vavr_dispensado"])
        )
        res = super().write(vals)
        # Mesmo corte do VT e da CCT: recalcula o rascunho da competência
        # corrente em diante e recusa o confirmado.
        self.env["hr.contract.advantage"]._l10n_br_vt_integridade(
            mudam._l10n_br_vavr_holerites()
        )
        return res
