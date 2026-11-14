# Copyright 2026 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import _, api, fields, models
from odoo.exceptions import UserError

CODIGOS_VT = ("VT", "VT_DIARIO")


class HrContractAdvantage(models.Model):
    _inherit = "hr.contract.advantage"

    def _l10n_br_vt_holerites(self):
        """Holerites vivos dos contratos cujo VT este registro altera."""
        contratos = self.filtered(
            lambda a: a.advantage_template_code in CODIGOS_VT
        ).contract_id
        if not contratos:
            return self.env["hr.payslip"]
        return (
            self.env["hr.payslip"]
            .sudo()
            .search([("contract_id", "in", contratos.ids), ("state", "!=", "cancel")])
        )

    def _l10n_br_vt_integridade(self, holerites):
        """Recalcula o holerite aberto e recusa o confirmado da competência vigente.

        O valor do VT muda o crédito e o desconto do mês. Holerite de
        competência já encerrada guarda o que valeu na época; o da competência
        corrente ou futura, confirmado, ficaria com um VT que o cadastro já não
        sustenta.
        """
        inicio_mes = fields.Date.context_today(self).replace(day=1)
        fechados = holerites.filtered(
            lambda r: r.state not in ("draft", "verify") and r.date_to >= inicio_mes
        )
        if fechados:
            raise UserError(
                _(
                    "Não é possível alterar o vale-transporte do contrato: o "
                    "holerite %(fechados)s já está confirmado e o crédito e o "
                    "desconto de VT dependem dele. Volte o confirmado para "
                    "rascunho primeiro.",
                    fechados=", ".join(fechados.mapped(lambda r: r.number or r.name)),
                )
            )
        holerites.filtered(
            lambda r: r.state in ("draft", "verify") and r.line_ids
        ).compute_sheet()

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        self._l10n_br_vt_integridade(records._l10n_br_vt_holerites())
        return records

    def write(self, vals):
        if not {"amount", "advantage_template_id", "contract_id"} & set(vals):
            return super().write(vals)
        antes = self._l10n_br_vt_holerites()
        res = super().write(vals)
        self._l10n_br_vt_integridade(antes | self._l10n_br_vt_holerites())
        return res

    def unlink(self):
        holerites = self._l10n_br_vt_holerites()
        res = super().unlink()
        self._l10n_br_vt_integridade(holerites)
        return res
