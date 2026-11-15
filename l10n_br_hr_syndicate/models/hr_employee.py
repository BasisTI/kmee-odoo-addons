# Copyright 2024 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class HrEmployee(models.Model):
    _inherit = "hr.employee"

    l10n_br_oposicao_contribuicao = fields.Boolean(
        string="Fez oposição à contribuição assistencial",
        groups="hr.group_hr_user",
        help="Direito de oposição do empregado: não paga a contribuição "
        "assistencial (617). A oposição prevalece sobre a marca de sindicalista "
        "e sobre a CCT. A escolha é individual, da pessoa, e vale para todos os "
        "contratos dela.",
    )
    l10n_br_sindicalista = fields.Boolean(
        string="Sindicalista",
        groups="hr.group_hr_user",
        help="Marca de sindicalista: a CCT diz quanto ele paga da contribuição "
        "assistencial (617: integral, metade ou nada) e só ele paga a "
        "contribuição sindical (602) da CCT.",
    )
    l10n_br_contribuicao_individual_ids = fields.One2many(
        comodel_name="l10n.br.hr.syndicate.individual.value",
        inverse_name="employee_id",
        string="Contribuição Sindical Individual (602)",
        groups="hr.group_hr_user",
    )

    _L10N_BR_CAMPOS_CONTRIBUICAO = (
        "l10n_br_oposicao_contribuicao",
        "l10n_br_sindicalista",
    )

    def _l10n_br_holerites_contribuicao(self):
        return (
            self.env["hr.payslip"]
            .sudo()
            .search(
                [
                    ("employee_id", "in", self.ids),
                    ("state", "!=", "cancel"),
                    ("l10n_br_fora_de_vigor", "=", False),
                ]
            )
        )

    def write(self, vals):
        if not set(self._L10N_BR_CAMPOS_CONTRIBUICAO) & set(vals):
            return super().write(vals)
        return self.env["hr.payslip"]._l10n_br_contribuicao_guardar(
            self._l10n_br_holerites_contribuicao(),
            lambda: super(HrEmployee, self).write(vals),
        )


class L10nBrHrSyndicateIndividualValue(models.Model):
    _name = "l10n.br.hr.syndicate.individual.value"
    _description = "Contribuição Sindical Individual (602) do Funcionário"
    _order = "employee_id, date_start desc"

    employee_id = fields.Many2one(
        comodel_name="hr.employee",
        string="Funcionário",
        required=True,
        ondelete="cascade",
        index=True,
    )
    date_start = fields.Date(string="Vigência Início", required=True)
    date_end = fields.Date(
        string="Vigência Fim",
        help="Vazio: vale sem data de término.",
    )
    amount = fields.Float(
        string="Valor Mensal (R$)",
        digits="Payroll",
        required=True,
        help="Valor mensal da contribuição sindical (602) deste funcionário. "
        "Prevalece sobre o da CCT e é devido mesmo sem a marca de sindicalista.",
    )

    _CAMPOS = ("employee_id", "date_start", "date_end", "amount")

    @api.constrains("employee_id", "date_start", "date_end")
    def _check_vigencia(self):
        for rec in self:
            if rec.date_end and rec.date_end < rec.date_start:
                raise ValidationError(
                    _(
                        "A vigência do valor individual de %s termina antes de "
                        "começar.",
                        rec.employee_id.display_name,
                    )
                )
            outro = self.search(
                [("id", "!=", rec.id), ("employee_id", "=", rec.employee_id.id)]
            ).filtered(
                lambda o, rec=rec: (not o.date_end or o.date_end >= rec.date_start)
                and (not rec.date_end or o.date_start <= rec.date_end)
            )
            if outro:
                raise ValidationError(
                    _(
                        "Os valores individuais de %s têm vigências que se "
                        "sobrepõem.",
                        rec.employee_id.display_name,
                    )
                )

    def valor_do_mes(self, competencia):
        """Valor vigente no dia 1 do mês de ``competencia``, ou ``None``.

        Como a ``Validity`` do Sistema DP: a vigência vale na competência se
        cobre o primeiro dia dela. Público para as regras salariais, que não
        alcançam nomes com ``_``.
        """
        inicio = competencia.replace(day=1)
        for rec in self.sorted("date_start", reverse=True):
            if rec.date_start <= inicio and (
                not rec.date_end or rec.date_end >= inicio
            ):
                return rec.amount
        return None

    def _holerites(self):
        return self.mapped("employee_id")._l10n_br_holerites_contribuicao()

    @api.model_create_multi
    def create(self, vals_list):
        empregados = self.env["hr.employee"].browse(
            [v["employee_id"] for v in vals_list if v.get("employee_id")]
        )
        return self.env["hr.payslip"]._l10n_br_contribuicao_guardar(
            empregados._l10n_br_holerites_contribuicao(),
            lambda: super(L10nBrHrSyndicateIndividualValue, self).create(vals_list),
        )

    def write(self, vals):
        if not set(vals) & set(self._CAMPOS):
            return super().write(vals)
        empregados = self.employee_id
        if vals.get("employee_id"):
            empregados |= self.env["hr.employee"].browse(vals["employee_id"])
        return self.env["hr.payslip"]._l10n_br_contribuicao_guardar(
            empregados._l10n_br_holerites_contribuicao(),
            lambda: super(L10nBrHrSyndicateIndividualValue, self).write(vals),
        )

    def unlink(self):
        return self.env["hr.payslip"]._l10n_br_contribuicao_guardar(
            self._holerites(),
            lambda: super(L10nBrHrSyndicateIndividualValue, self).unlink(),
        )
