# Copyright 2024 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import fields, models


class HrLeave(models.Model):
    _inherit = "hr.leave"

    l10n_br_aviso_ferias_data = fields.Date(
        string="Aviso de Férias Emitido em",
        copy=False,
        readonly=True,
        help="Data da primeira emissão do aviso de férias (CLT art. 135). "
        "Gravada na primeira impressão: a reimpressão repete a data, e o prazo "
        "de 30 dias é medido contra ela.",
    )
