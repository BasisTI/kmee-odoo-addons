# Copyright 2024 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import api, fields, models


class L10nBrHrSyndicateContribution(models.Model):
    _name = "l10n.br.hr.syndicate.contribution"
    _description = "Contribuição Sindical"
    _order = "year desc, month desc"

    partner_union_id = fields.Many2one(
        comodel_name="res.partner",
        string="Sindicato",
        domain=[("union_entity_code", "!=", False)],
        required=True,
    )
    year = fields.Integer(
        string="Ano",
        required=True,
    )
    month = fields.Selection(
        selection=[
            ("1", "Janeiro"),
            ("2", "Fevereiro"),
            ("3", "Março"),
            ("4", "Abril"),
            ("5", "Maio"),
            ("6", "Junho"),
            ("7", "Julho"),
            ("8", "Agosto"),
            ("9", "Setembro"),
            ("10", "Outubro"),
            ("11", "Novembro"),
            ("12", "Dezembro"),
        ],
        string="Mês de Desconto",
        required=True,
        help="Mês em que a contribuição é descontada do empregado.",
    )
    contribution_type = fields.Selection(
        selection=[
            ("assistencial", "Contribuição Assistencial"),
            ("confederativa", "Contribuição Confederativa"),
            ("sindical", "Contribuição Sindical (ex-imposto)"),
        ],
        string="Tipo",
        required=True,
        default="assistencial",
    )
    calc_method = fields.Selection(
        selection=[
            ("percent", "Percentual do Salário"),
            ("fixed", "Valor Fixo"),
            ("one_day", "Um Dia de Salário"),
        ],
        string="Método de Cálculo",
        required=True,
        default="percent",
    )
    percentage = fields.Float(
        string="Percentual (%)",
        help="Percentual sobre o salário bruto.",
    )
    fixed_amount = fields.Float(
        string="Valor Fixo",
        digits="Payroll",
    )
    active = fields.Boolean(default=True)

    _CONTRIBUICAO_CAMPOS = (
        "partner_union_id",
        "year",
        "month",
        "contribution_type",
        "calc_method",
        "percentage",
        "fixed_amount",
        "active",
    )

    def amount_for(self, wage):
        """Valor da contribuição sobre o salário ``wage``.

        Um dia de salário usa o mês comercial de 30 dias, como a folha.
        """
        self.ensure_one()
        if self.calc_method == "percent":
            return round(wage * self.percentage / 100.0, 2)
        if self.calc_method == "fixed":
            return self.fixed_amount
        return round(wage / 30.0, 2)

    def _contribuicao_snapshot(self):
        return {
            rec.id: tuple(
                str(rec._fields[n].convert_to_write(rec[n], rec))
                for n in self._CONTRIBUICAO_CAMPOS
            )
            for rec in self
        }

    def _contribuicao_holerites(self):
        """Holerites do mês de desconto de contratos com CCT deste sindicato."""
        slips = self.env["hr.payslip"]
        for rec in self.filtered("id"):
            candidatos = (
                self.env["hr.payslip"]
                .sudo()
                .search(
                    [
                        ("state", "!=", "cancel"),
                        ("l10n_br_fora_de_vigor", "=", False),
                        (
                            "contract_id.l10n_br_cct_id.partner_union_id",
                            "=",
                            rec.partner_union_id.id,
                        ),
                    ]
                )
            )
            slips |= candidatos.filtered(
                lambda s, rec=rec: s.date_to
                and (s.date_to.year, str(s.date_to.month)) == (rec.year, rec.month)
                and s.contract_id._l10n_br_cct_vigente(s.date_to).partner_union_id
                == rec.partner_union_id
            )
        return slips

    def _contribuicao_guardar(self, operacao):
        """Como a CCT: o que muda o desconto recalcula o aberto e recusa o confirmado."""
        if self.env.context.get("l10n_br_cct_guardando"):
            return operacao(self)
        contexto = self.with_context(l10n_br_cct_guardando=True)
        antes = self._contribuicao_snapshot()
        slips = self._contribuicao_holerites()
        res = operacao(contexto)
        existentes = self.exists()
        mudou = len(existentes) != len(self) or any(
            antes[i] != v for i, v in existentes._contribuicao_snapshot().items()
        )
        if mudou:
            self.env["l10n.br.hr.collective.convention"]._cct_aplicar_aos_holerites(
                slips | existentes._contribuicao_holerites()
            )
        return res

    @api.model_create_multi
    def create(self, vals_list):
        recs = super(
            L10nBrHrSyndicateContribution,
            self.with_context(l10n_br_cct_guardando=True),
        ).create(vals_list)
        recs = recs.with_env(self.env)
        self.env["l10n.br.hr.collective.convention"]._cct_aplicar_aos_holerites(
            recs._contribuicao_holerites()
        )
        return recs

    def write(self, vals):
        if not set(vals) & set(self._CONTRIBUICAO_CAMPOS):
            return super().write(vals)
        return self._contribuicao_guardar(
            lambda recs: super(L10nBrHrSyndicateContribution, recs).write(vals)
        )

    def unlink(self):
        return self._contribuicao_guardar(
            lambda recs: super(L10nBrHrSyndicateContribution, recs).unlink()
        )
