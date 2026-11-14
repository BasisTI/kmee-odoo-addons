# Copyright 2026 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

CODIGOS_VT = ("VT", "VT_DIARIO")
# Regras de VT: só o holerite cuja estrutura as tem depende do cadastro de VT.
REGRAS_VT = ("DESC_VT", "VT_INFO")


class HrContractAdvantage(models.Model):
    _inherit = "hr.contract.advantage"

    def _l10n_br_vt_holerites(self):
        """Holerites vivos dos contratos cujo VT este registro altera."""
        contratos = self.filtered(
            lambda a: a.advantage_template_code in CODIGOS_VT
        ).contract_id
        if not contratos:
            return self.env["hr.payslip"]
        holerites = (
            self.env["hr.payslip"]
            .sudo()
            .search([("contract_id", "in", contratos.ids), ("state", "!=", "cancel")])
        )
        # 13º, recibo de férias e demais estruturas sem regra de VT não dependem
        # do cadastro: não recusam nem são recalculados. As regras são as que o
        # próprio holerite calcula (estrutura e pais).
        return holerites.filtered(
            lambda r: set(REGRAS_VT) & set(r._get_salary_rules().mapped("code"))
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
        # Rascunho de competência encerrada guarda o que valeu: recalculá-lo com
        # os dados de hoje mudaria o líquido por outra causa.
        holerites.filtered(
            lambda r: r.state in ("draft", "verify")
            and r.line_ids
            and r.date_to >= inicio_mes
        ).compute_sheet()

    @api.constrains("amount", "advantage_template_id", "contract_id")
    def _check_vt_mensal_ou_diario(self):
        """VT mensal e valor diário juntos: o diário prevaleceria e o mensal
        seria ignorado sem aviso."""
        for contrato in self.contract_id:
            ativos = contrato.advantages_ids.filtered(
                lambda a: a.amount and a.advantage_template_code in CODIGOS_VT
            )
            if set(ativos.mapped("advantage_template_code")) == set(CODIGOS_VT):
                raise ValidationError(
                    _(
                        "O contrato %(contrato)s tem vale-transporte mensal (VT) e "
                        "por valor diário (VT_DIARIO) ao mesmo tempo. Use um só: "
                        "zere ou remova o outro.",
                        contrato=contrato.display_name,
                    )
                )

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
