# Copyright 2024 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class ESocialS1010(models.Model):
    _name = "l10n_br.esocial.s1010"
    _inherit = "l10n_br.esocial.base.intermediario"
    _description = "eSocial S-1010 - Tabela de Rubricas"

    salary_rule_id = fields.Many2one(
        "hr.salary.rule",
        string="Regra Salarial",
        required=True,
        ondelete="cascade",
    )
    operacao = fields.Selection(
        [
            ("inclusao", "Inclusão"),
            ("alteracao", "Alteração"),
            ("exclusao", "Exclusão"),
        ],
        string="Operação",
        default="inclusao",
        required=True,
    )
    ini_valid = fields.Char(
        string="Início Validade",
        size=7,
        required=True,
        help="Formato AAAA-MM",
    )
    fim_valid = fields.Char(
        string="Fim Validade",
        size=7,
    )

    @api.model
    def criar_para_regras(self, regras, ini_valid, operacao="inclusao"):
        """Cria um S-1010 por rubrica, não por regra.

        Regras de estruturas diferentes (mensal, férias, 13º, rescisão) repetem
        o código eSocial; o governo recusa a rubrica declarada duas vezes.
        """
        criados = self.browse()
        vistos = set()
        for regra in regras.filtered("l10n_br_esocial_cod_rubr"):
            chave = regra._esocial_chave_rubrica()
            if chave in vistos:
                continue
            vistos.add(chave)
            criados |= self.create(
                {
                    "salary_rule_id": regra.id,
                    "operacao": operacao,
                    "ini_valid": ini_valid,
                }
            )
        return criados

    @api.constrains("salary_rule_id", "operacao", "ini_valid", "company_id")
    def _check_rubrica_unica(self):
        for rec in self:
            regra = rec.salary_rule_id
            if not regra.l10n_br_esocial_cod_rubr:
                continue
            chave = regra._esocial_chave_rubrica()
            repetidos = self.search(
                [
                    ("id", "!=", rec.id),
                    ("company_id", "=", rec.company_id.id),
                    ("operacao", "=", rec.operacao),
                    ("ini_valid", "=", rec.ini_valid),
                    ("salary_rule_id.l10n_br_esocial_cod_rubr", "=", chave[0]),
                ]
            ).filtered(
                lambda r, chave=chave: r.salary_rule_id._esocial_chave_rubrica()
                == chave
            )
            if repetidos:
                raise ValidationError(
                    _(
                        "A rubrica '%(cod)s' já tem S-1010 de %(op)s com início "
                        "de validade %(ini)s para esta empresa (regra "
                        "'%(outra)s'). Cada código de rubrica entra uma vez."
                    )
                    % {
                        "cod": chave[0],
                        "op": rec.operacao,
                        "ini": rec.ini_valid,
                        "outra": repetidos[0].salary_rule_id.display_name,
                    }
                )

    def _get_event_type(self):
        return "S-1010"

    def _to_esociallib_dict(self):
        self.ensure_one()
        rule = self.salary_rule_id

        if not rule.l10n_br_esocial_cod_rubr:
            raise UserError(f"Regra '{rule.name}' não possui Código Rubrica eSocial.")
        if not rule.l10n_br_esocial_nat_rubr_id:
            raise UserError(
                f"Regra '{rule.name}' não possui Natureza de Rubrica eSocial."
            )
        if not rule.l10n_br_esocial_tp_rubr:
            raise UserError(f"Regra '{rule.name}' não possui Tipo de Rubrica eSocial.")

        ide = self._get_ide_empregador()
        proc = self._get_proc_info()

        data = {
            "tp_insc": ide["tp_insc"],
            "nr_insc": ide["nr_insc"],
            "operacao": self.operacao,
            "cod_rubr": rule.l10n_br_esocial_cod_rubr,
            "ide_tab_rubr": rule.l10n_br_esocial_ide_tab_rubr or "1",
            "ini_valid": self.ini_valid,
            "proc_emi": proc["proc_emi"],
            "ver_proc": proc["ver_proc"],
        }

        if self.fim_valid:
            data["fim_valid"] = self.fim_valid

        # dadosRubrica (required for inclusao/alteracao)
        if self.operacao in ("inclusao", "alteracao"):
            data.update(
                {
                    "dsc_rubr": rule.name,
                    "nat_rubr": int(rule.l10n_br_esocial_nat_rubr_id.codigo),
                    "tp_rubr": int(rule.l10n_br_esocial_tp_rubr),
                    "cod_inc_cp": rule.l10n_br_esocial_cod_inc_cp or "00",
                    "cod_inc_irrf": int(rule.l10n_br_esocial_cod_inc_irrf or "0"),
                    "cod_inc_fgts": rule.l10n_br_esocial_cod_inc_fgts or "00",
                }
            )

        return data
