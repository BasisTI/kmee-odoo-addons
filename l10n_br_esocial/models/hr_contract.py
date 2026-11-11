# Copyright 2024 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import fields, models


class HrContract(models.Model):
    _inherit = "hr.contract"

    l10n_br_esocial_motivo_deslig_id = fields.Many2one(
        "l10n_br.esocial.motivo.desligamento",
        string="Motivo Desligamento eSocial",
        help="Motivo do desligamento conforme Tabela 19 do eSocial.",
    )
    l10n_br_esocial_tp_jornada = fields.Selection(
        selection=[
            ("2", "2 - Jornada 12 x 36"),
            ("3", "3 - Horário diário fixo e folga variável"),
            ("4", "4 - Horário diário fixo e folga fixa (no domingo)"),
            ("5", "5 - Horário diário fixo e folga fixa (exceto no domingo)"),
            (
                "6",
                "6 - Horário diário fixo e folga fixa (em outro dia da semana), "
                "com folga adicional periódica no domingo",
            ),
            ("7", "7 - Turno ininterrupto de revezamento"),
            ("9", "9 - Demais tipos de jornada"),
        ],
        string="Tipo de Jornada eSocial",
        help="Campo tpJornada do S-2200 (leiaute S-1.3). Não há valor padrão: "
        "o evento é recusado enquanto estiver vazio.",
    )
    l10n_br_esocial_tmp_parc = fields.Selection(
        selection=[
            ("0", "0 - Não é contrato em tempo parcial"),
            ("1", "1 - Limitado a 25 horas semanais"),
            ("2", "2 - Limitado a 30 horas semanais"),
            ("3", "3 - Limitado a 26 horas semanais"),
        ],
        string="Tempo Parcial eSocial",
        default="0",
        help="Campo tmpParc do S-2200 (leiaute S-1.3).",
    )
