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
        "de 30 dias é medido contra ela, enquanto o período for o avisado.",
    )
    l10n_br_aviso_ferias_inicio = fields.Date(
        string="Início Avisado", copy=False, readonly=True
    )
    l10n_br_aviso_ferias_fim = fields.Date(
        string="Fim Avisado", copy=False, readonly=True
    )

    def _split_leaves(self, split_date_from, split_date_to):
        # As peças de uma ausência dividida herdam a comunicação já feita.
        return super(
            HrLeave, self.with_context(l10n_br_herdar_aviso_ferias=True)
        )._split_leaves(split_date_from, split_date_to)

    def copy_data(self, default=None):
        valores = super().copy_data(default)
        if self.env.context.get("l10n_br_herdar_aviso_ferias"):
            for leave, vals in zip(self, valores, strict=False):
                if leave.l10n_br_aviso_ferias_data:
                    vals.update(
                        {
                            "l10n_br_aviso_ferias_data": leave.l10n_br_aviso_ferias_data,
                            "l10n_br_aviso_ferias_inicio": leave.l10n_br_aviso_ferias_inicio,
                            "l10n_br_aviso_ferias_fim": leave.l10n_br_aviso_ferias_fim,
                        }
                    )
        return valores
