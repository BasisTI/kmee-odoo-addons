# Copyright 2026 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import fields, models


class HrLeaveType(models.Model):
    _inherit = "hr.leave.type"

    l10n_br_esocial_salario_maternidade = fields.Boolean(
        string="Licença-maternidade (eSocial)",
        help="O salário dos dias deste afastamento é salário-maternidade pago "
        "pelo empregador (compensado na GPS): no S-1200 vai na rubrica de "
        "salário-maternidade (natureza 4050) da regra salarial, não na de "
        "salário comum.",
    )
