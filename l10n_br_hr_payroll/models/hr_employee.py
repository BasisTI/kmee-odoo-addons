# Copyright 2024 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class HrEmployee(models.Model):
    _inherit = "hr.employee"

    l10n_br_tipo_contrato = fields.Selection(
        selection=[
            ("clt", "CLT"),
            ("estatutario", "Estatutário"),
            ("aprendiz", "Aprendiz"),
            ("temporario", "Temporário"),
        ],
        string="Tipo de Contrato",
        default="clt",
    )
    l10n_br_irrf_dependentes = fields.Integer(
        string="Dependentes IRRF",
        default=0,
    )
    l10n_br_pensao_alimenticia = fields.Float(
        string="Pensão Alimentícia (Valor Fixo)",
        default=0.0,
        help="Parcela fixa mensal de pensão alimentícia determinada "
        "judicialmente. Somada à parcela percentual (se houver).",
    )
    l10n_br_pensao_percentual = fields.Float(
        string="Pensão Alimentícia (% da Remuneração)",
        default=0.0,
        help="Percentual da remuneração bruta destinado à pensão alimentícia "
        "(ex.: 30 = 30%). O valor efetivo descontado é: valor fixo + "
        "percentual sobre a remuneração bruta do mês.",
    )
    l10n_br_pensao_fgts_percentual = fields.Float(
        string="Pensão sobre o FGTS (% do saldo)",
        default=0.0,
        help="Percentual do saldo do FGTS retido para pensão alimentícia por "
        "decisão judicial própria (S-2299 percAliment; TRCT, campo 29). É outra "
        "base que a pensão da folha e não entra no cálculo da rescisão.",
    )
    l10n_br_pensao_fgts_valor = fields.Float(
        string="Pensão sobre o FGTS (valor)",
        default=0.0,
        help="Valor fixo retido do saldo do FGTS para pensão alimentícia por "
        "decisão judicial própria (S-2299 vrAlim). Pode somar-se ao percentual.",
    )
    l10n_br_pensao_fgts_origem = fields.Char(
        string="Origem da pensão sobre o FGTS",
        help="Decisão judicial que fixou a retenção sobre o FGTS (vara e "
        "número do processo).",
    )
    l10n_br_molestia_grave = fields.Boolean(
        string="Portador de Moléstia Grave",
        help="Isenção de IRRF conforme Lei 7.713/88",
    )
    l10n_br_cid_molestia = fields.Char(
        string="CID da Moléstia",
    )
    l10n_br_pcd = fields.Boolean(
        string="Pessoa com Deficiência",
    )
    l10n_br_num_filhos_sf = fields.Integer(
        string="Filhos para Salário Família",
        help="Filhos até 14 anos ou inválidos de qualquer idade",
        default=0,
    )
    l10n_br_filhos_invalidos_sf = fields.Integer(
        string="Filhos Inválidos (Salário Família)",
        help="Filhos inválidos de qualquer idade que recebem salário família",
        default=0,
    )

    @api.constrains("l10n_br_pensao_fgts_percentual", "l10n_br_pensao_fgts_valor")
    def _check_pensao_fgts(self):
        for rec in self:
            if not 0 <= rec.l10n_br_pensao_fgts_percentual <= 100:
                raise ValidationError(
                    _("O percentual da pensão sobre o FGTS deve ficar entre 0 e 100.")
                )
            if rec.l10n_br_pensao_fgts_valor < 0:
                raise ValidationError(
                    _("O valor da pensão sobre o FGTS não pode ser negativo.")
                )
