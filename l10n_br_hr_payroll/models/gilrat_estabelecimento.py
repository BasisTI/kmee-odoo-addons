# Copyright 2024 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""RAT e FAP por estabelecimento, com vigência (TG-122).

O FAP é publicado todo ano por CNPJ (Lei 10.666/2003, art. 10) e o RAT segue o
CNAE preponderante de cada estabelecimento: matriz e filiais podem ter valores
diferentes na mesma competência. Os campos da empresa (``l10n_br_hr_rat`` e
``l10n_br_hr_fap``) continuam como valor PADRÃO; esta tabela só precisa ter
linha para o estabelecimento que diverge.

O estabelecimento do contrato é o mesmo que o S-2200 usa como local de
trabalho: o CNPJ do **Endereço de Trabalho** do empregado
(``hr.employee.address_id``). Assim não existem dois conceitos de filial.
"""
import re

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

from . import salary_rules_br


def so_digitos(valor):
    return re.sub(r"\D", "", valor or "")


class L10nBrHrPayrollGilrat(models.Model):
    _name = "l10n_br.hr.payroll.gilrat"
    _description = "RAT/FAP por Estabelecimento (com vigência)"
    _order = "company_id, cnpj, date_start desc"

    name = fields.Char(compute="_compute_name", store=True)
    company_id = fields.Many2one(
        "res.company",
        string="Empresa",
        required=True,
        default=lambda self: self.env.company,
        index=True,
    )
    cnpj = fields.Char(
        string="CNPJ do Estabelecimento",
        size=18,
        required=True,
        help="CNPJ de 14 dígitos do estabelecimento (matriz ou filial): o mesmo "
        "CNPJ do Endereço de Trabalho do empregado, que é o local de trabalho "
        "do S-2200. Aceita pontuação.",
    )
    date_start = fields.Date(
        string="Início da Vigência",
        required=True,
        help="Primeiro dia do mês de início (o S-1005 tem validade mensal).",
    )
    date_end = fields.Date(
        string="Fim da Vigência",
        help="Último dia do mês de fim. Vazio = vigência em aberto.",
    )
    rat = fields.Selection(
        selection=[
            ("1", "1% - risco leve"),
            ("2", "2% - risco médio"),
            ("3", "3% - risco grave"),
        ],
        string="Alíquota RAT",
        required=True,
    )
    fap = fields.Float(
        string="FAP",
        digits=(5, 4),
        required=True,
        default=1.0,
        help="Fator Acidentário de Prevenção do estabelecimento no período, "
        "de 0,5000 a 2,0000 (Decreto 3.048/99, art. 202-A).",
    )
    rat_ajustado = fields.Float(
        string="RAT Ajustado (%)",
        digits=(5, 4),
        compute="_compute_rat_ajustado",
        store=True,
    )

    @api.depends("cnpj", "date_start")
    def _compute_name(self):
        for rec in self:
            rec.name = "%s - %s" % (rec.cnpj or "", rec.date_start or "")

    @api.depends("rat", "fap")
    def _compute_rat_ajustado(self):
        for rec in self:
            rec.rat_ajustado = salary_rules_br.aliquota_rat_ajustado(
                float(rec.rat or 0), rec.fap
            )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("cnpj"):
                vals["cnpj"] = so_digitos(vals["cnpj"])
        return super().create(vals_list)

    def write(self, vals):
        if vals.get("cnpj"):
            vals = dict(vals, cnpj=so_digitos(vals["cnpj"]))
        return super().write(vals)

    @api.constrains("fap")
    def _check_fap(self):
        for rec in self:
            if not 0.5 <= rec.fap <= 2.0:
                raise ValidationError(
                    _(
                        "O FAP do estabelecimento %(cnpj)s deve estar entre "
                        "0,5000 e 2,0000 (Decreto 3.048/99, art. 202-A). Valor "
                        "informado: %(valor)s."
                    )
                    % {"cnpj": rec.cnpj, "valor": rec.fap}
                )

    @api.constrains("cnpj")
    def _check_cnpj(self):
        for rec in self:
            if len(so_digitos(rec.cnpj)) != 14:
                raise ValidationError(
                    _("O CNPJ do estabelecimento deve ter 14 dígitos (%s).") % rec.cnpj
                )

    @api.constrains("date_start", "date_end")
    def _check_vigencia(self):
        for rec in self:
            if rec.date_start.day != 1:
                raise ValidationError(
                    _("O início da vigência deve ser o primeiro dia de um mês.")
                )
            if rec.date_end:
                if rec.date_end < rec.date_start:
                    raise ValidationError(_("O fim da vigência é anterior ao início."))
                if (rec.date_end + fields.date.resolution).day != 1:
                    raise ValidationError(
                        _("O fim da vigência deve ser o último dia de um mês.")
                    )
            outros = self.search(
                [
                    ("id", "!=", rec.id),
                    ("company_id", "=", rec.company_id.id),
                    ("cnpj", "=", rec.cnpj),
                    "|",
                    ("date_end", "=", False),
                    ("date_end", ">=", rec.date_start),
                ]
            ).filtered(
                lambda o, rec=rec: not rec.date_end or o.date_start <= rec.date_end
            )
            if outros:
                raise ValidationError(
                    _(
                        "O estabelecimento %(cnpj)s já tem RAT/FAP com vigência "
                        "que se sobrepõe a esta (%(outro)s)."
                    )
                    % {"cnpj": rec.cnpj, "outro": outros[0].display_name}
                )

    @api.model
    def _vigente(self, company, cnpj, competencia):
        """Linha do estabelecimento ``cnpj`` vigente na ``competencia``.

        Devolve um recordset vazio quando não há linha: o chamador usa então o
        valor padrão da empresa.
        """
        cnpj = so_digitos(cnpj)
        if not cnpj or not competencia:
            return self.browse()
        return self.search(
            [
                ("company_id", "=", company.id),
                ("cnpj", "=", cnpj),
                ("date_start", "<=", competencia),
                "|",
                ("date_end", "=", False),
                ("date_end", ">=", competencia),
            ],
            limit=1,
        )
