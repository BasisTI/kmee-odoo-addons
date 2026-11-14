# Copyright 2024 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from dateutil.relativedelta import relativedelta

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

    # Tipo de contratação que não conta como período de experiência (regra do DP).
    _L10N_BR_PRAZO_DETERMINADO = "prazo determinado"
    _L10N_BR_CAMPOS_CONTRIBUICAO = ("contract_type_id", "trial_date_end")

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

    def _l10n_br_prazo_determinado(self):
        self.ensure_one()
        nome = (self.contract_type_id.name or "").strip().casefold()
        return nome == self._L10N_BR_PRAZO_DETERMINADO

    def _l10n_br_em_experiencia(self, competencia):
        """Em experiência no último dia da competência.

        Contrato por prazo determinado não conta como experiência, mesmo com as
        datas de experiência preenchidas. Quem termina a experiência no meio do
        mês já deve o mês inteiro.
        """
        self.ensure_one()
        if self._l10n_br_prazo_determinado() or not self.trial_date_end:
            return False
        fim_do_mes = competencia.replace(day=1) + relativedelta(months=1, days=-1)
        return self.trial_date_end >= fim_do_mes

    def _l10n_br_contribuicao_resolver(self, competencia, tipo):
        """``(valor, motivo)`` da contribuição sindical do contrato na competência.

        ``valor`` ``None`` é célula em branco: sem CCT, sem regra cadastrada para
        o sindicato na competência e sem valor individual, a lacuna de cadastro
        não vira isenção. ``motivo`` diz por que o valor não é o cheio:
        ``oposicao``, ``tipo_contratacao``, ``experiencia``,
        ``sindicalizado_metade``, ``sindicalizado_isento`` ou
        ``valor_individual``.

        617 (``assistencial``): a oposição vence a marca de sindicalista; depois
        as isenções da CCT (tipo de contratação, experiência); depois o
        sindicalista paga integral, metade ou nada conforme a CCT. 602
        (``sindical``): o valor individual do funcionário prevalece e é devido
        mesmo sem a marca; senão só o sindicalista paga o valor da CCT. Os demais
        tipos seguem o valor cadastrado, sem regra individual.
        """
        self.ensure_one()
        base = None
        cct = self._l10n_br_cct_vigente(competencia) if competencia else False
        if cct and competencia:
            contribuicoes = self.env["l10n.br.hr.syndicate.contribution"].search(
                [
                    ("partner_union_id", "=", cct.partner_union_id.id),
                    ("year", "=", competencia.year),
                    ("month", "=", str(competencia.month)),
                    ("contribution_type", "=", tipo),
                ]
            )
            if contribuicoes:
                base = sum(c.amount_for(self.wage) for c in contribuicoes)
        empregado = self.employee_id.sudo()
        if tipo == "sindical" and competencia:
            individual = empregado.l10n_br_contribuicao_individual_ids.valor_do_mes(
                competencia
            )
            if individual is not None:
                return individual, "valor_individual"
            if base is None or not empregado.l10n_br_sindicalista:
                return None, False
            return base, False
        if base is None:
            return None, False
        if tipo != "assistencial":
            return base, False
        if empregado.l10n_br_oposicao_contribuicao:
            return 0.0, "oposicao"
        if self.contract_type_id in cct.assistencial_exempt_contract_type_ids:
            return 0.0, "tipo_contratacao"
        if cct.assistencial_exempt_trial and self._l10n_br_em_experiencia(competencia):
            return 0.0, "experiencia"
        if empregado.l10n_br_sindicalista:
            fator = cct.assistencial_fator_sindicalizado()
            if fator == 1.0:
                return base, False
            motivo = "sindicalizado_metade" if fator else "sindicalizado_isento"
            return round(base * fator, 2), motivo
        return base, False

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

    def _l10n_br_write_contribuicao(self, vals):
        """Tipo de contratação e experiência mudam a 617: recalcula o aberto."""
        antes = {c.id: (c.contract_type_id, c.trial_date_end) for c in self.sudo()}
        res = self.with_context(l10n_br_contribuicao_guardando=True).write(vals)
        mudaram = self.sudo().filtered(
            lambda c: (c.contract_type_id, c.trial_date_end) != antes[c.id]
        )
        self.env["l10n.br.hr.collective.convention"]._cct_aplicar_aos_holerites(
            mudaram._l10n_br_holerites_cct()
        )
        return res

    def write(self, vals):
        if set(vals) & set(self._L10N_BR_CAMPOS_CONTRIBUICAO) and not (
            self.env.context.get("l10n_br_contribuicao_guardando")
        ):
            return self._l10n_br_write_contribuicao(vals)
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
