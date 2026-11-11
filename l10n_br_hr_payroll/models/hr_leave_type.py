# Copyright 2024 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import fields, models


class HrLeaveType(models.Model):
    _inherit = "hr.leave.type"

    l10n_br_afastamento_inss = fields.Boolean(
        string="Afastamento Previdenciário",
        help="A empresa paga os 15 primeiros dias de afastamento (Lei 8.213/91, "
        "art. 60, § 3º). Os dias seguintes são pagos pelo INSS e saem do "
        "salário do holerite.",
    )
