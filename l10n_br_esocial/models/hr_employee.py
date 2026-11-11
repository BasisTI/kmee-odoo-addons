# Copyright 2024 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import fields, models


class HrEmployee(models.Model):
    _inherit = "hr.employee"

    l10n_br_esocial_matricula = fields.Char(
        string="Matrícula eSocial",
        size=30,
        help="Matrícula atribuída ao trabalhador pela empresa.",
    )
    l10n_br_esocial_categoria_id = fields.Many2one(
        "l10n_br.esocial.categoria.trabalhador",
        string="Categoria Trabalhador eSocial",
        help="Categoria do trabalhador conforme Tabela 1 do eSocial.",
    )
    l10n_br_esocial_grau_instr = fields.Selection(
        selection=[
            ("01", "01 - Analfabeto"),
            ("02", "02 - Até o 5º ano incompleto do ensino fundamental"),
            ("03", "03 - 5º ano completo do ensino fundamental"),
            ("04", "04 - Do 6º ao 9º ano do ensino fundamental incompleto"),
            ("05", "05 - Ensino fundamental completo"),
            ("06", "06 - Ensino médio incompleto"),
            ("07", "07 - Ensino médio completo"),
            ("08", "08 - Educação superior incompleta"),
            ("09", "09 - Educação superior completa"),
            ("10", "10 - Pós-graduação completa"),
            ("11", "11 - Mestrado completo"),
            ("12", "12 - Doutorado completo"),
        ],
        string="Grau de Instrução eSocial",
        groups="hr.group_hr_user",
        help="Grau de instrução do trabalhador (campo grauInstr do S-2200, "
        "leiaute S-1.3). O campo 'Nível de Certificado' do Odoo não tem a "
        "mesma granularidade e não serve de origem.",
    )
