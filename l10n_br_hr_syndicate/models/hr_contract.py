# Copyright 2024 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class HrContract(models.Model):
    _inherit = "hr.contract"

    l10n_br_cct_id = fields.Many2one(
        comodel_name="l10n.br.hr.collective.convention",
        string="Convenção Coletiva (CCT)",
        domain="[('partner_union_id', '=', partner_union)] if partner_union else []",
        index=True,
        help="CCT do contrato. As regras salariais leem pisos, contribuições e "
        "percentuais da CCT vigente na competência do holerite: a escolhida, se "
        "a vigência cobre a competência, ou a do mesmo sindicato que a cobre "
        "(a sucessora, depois de um dissídio). Sem CCT, o contrato segue como "
        "antes: as regras usam os parâmetros que tiverem.",
    )

    @api.constrains("l10n_br_cct_id", "partner_union")
    def _check_l10n_br_cct_sindicato(self):
        for rec in self:
            cct = rec.l10n_br_cct_id
            if cct and rec.partner_union and cct.partner_union_id != rec.partner_union:
                raise ValidationError(
                    _(
                        "A CCT %(cct)s é do sindicato %(cct_sind)s, e o contrato "
                        "está no sindicato %(sind)s.",
                        cct=cct.display_name,
                        cct_sind=cct.partner_union_id.display_name,
                        sind=rec.partner_union.display_name,
                    )
                )

    @api.onchange("l10n_br_cct_id")
    def _onchange_l10n_br_cct_id(self):
        if self.l10n_br_cct_id:
            self.partner_union = self.l10n_br_cct_id.partner_union_id

    def _l10n_br_cct_resolver(self, data):
        """``(CCT, motivo)`` do contrato em ``data``; ``motivo`` falso se a CCT cobre.

        A CCT do contrato vale se a vigência cobre ``data``; senão vale a ativa
        do mesmo sindicato que cobre (a CCT trocada no meio do ano). Sem nenhuma
        cobrindo, o desconto nunca zera em silêncio: vale a última vencida do
        mesmo sindicato (``motivo`` "vencida"), a primeira se ``data`` é anterior
        a todas ("futura") ou a própria CCT do contrato se ela foi arquivada e o
        sindicato não tem outra ativa ("arquivada"). O holerite mostra o aviso.
        Sem CCT no contrato: vazio.
        """
        self.ensure_one()
        convencao = self.env["l10n.br.hr.collective.convention"]
        cct = self.l10n_br_cct_id
        if not cct or not data:
            return convencao, False
        if cct.active and cct.date_start <= data <= cct.date_end:
            return cct, False
        sindicato = [("partner_union_id", "=", cct.partner_union_id.id)]
        cobre = convencao.search(
            sindicato + [("date_start", "<=", data), ("date_end", ">=", data)],
            limit=1,
        )
        if cobre:
            return cobre, False
        vencida = convencao.search(
            sindicato + [("date_end", "<", data)], order="date_end desc", limit=1
        )
        if vencida:
            return vencida, "vencida"
        futura = convencao.search(
            sindicato + [("date_start", ">", data)], order="date_start", limit=1
        )
        if futura:
            return futura, "futura"
        return cct, "arquivada"

    def _l10n_br_cct_vigente(self, data):
        """CCT do contrato em ``data``, a última vencida se nenhuma cobre."""
        self.ensure_one()
        return self._l10n_br_cct_resolver(data)[0]

    def _l10n_br_holerites_cct(self):
        return (
            self.env["hr.payslip"]
            .sudo()
            .search(
                [
                    ("contract_id", "in", self.ids),
                    ("state", "!=", "cancel"),
                    ("l10n_br_fora_de_vigor", "=", False),
                ]
            )
        )

    @api.model_create_multi
    def create(self, vals_list):
        vals_list = [self._l10n_br_sindicato_da_cct(v) for v in vals_list]
        return super().create(vals_list)

    @api.model
    def _l10n_br_sindicato_da_cct(self, vals):
        """CCT sem sindicato informado: o sindicato é o da CCT."""
        if vals.get("l10n_br_cct_id") and not vals.get("partner_union"):
            cct = self.env["l10n.br.hr.collective.convention"].browse(
                vals["l10n_br_cct_id"]
            )
            vals = dict(vals, partner_union=cct.partner_union_id.id)
        return vals

    def write(self, vals):
        if "l10n_br_cct_id" not in vals and "partner_union" not in vals:
            return super().write(vals)
        if vals.get("l10n_br_cct_id") and "partner_union" not in vals:
            # Contrato sem sindicato ganha o da CCT; com sindicato, a CCT de outro
            # sindicato é recusada pela restrição em vez de trocar o sindicato.
            sem_sindicato = self.filtered(lambda c: not c.partner_union)
            if sem_sindicato and sem_sindicato != self:
                sem_sindicato.write(vals)
                return (self - sem_sindicato).write(vals)
            if sem_sindicato:
                vals = self._l10n_br_sindicato_da_cct(vals)
        slips = self._l10n_br_holerites_cct()
        antes = {s.id: s.contract_id._l10n_br_cct_vigente(s.date_to) for s in slips}
        res = super().write(vals)
        mudaram = slips.filtered(
            lambda s: s.contract_id._l10n_br_cct_vigente(s.date_to) != antes[s.id]
        )
        self.env["l10n.br.hr.collective.convention"]._cct_aplicar_aos_holerites(mudaram)
        return res
