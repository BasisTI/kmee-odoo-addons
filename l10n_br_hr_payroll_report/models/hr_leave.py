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

    def copy_data(self, default=None):
        """Peça de ausência dividida herda a comunicação já feita.

        O Odoo divide a ausência em dois lugares (``_split_leaves``, na folga
        em lote, e ``hr.contract.write``, na mudança de contrato) e os dois
        criam as peças por ``copy_data`` com as novas datas. Aqui mora a regra
        única: a peça cujo período cabe no avisado leva a data e o período.
        """
        valores = super().copy_data(default)
        novas = default or {}
        if "request_date_from" in novas and "request_date_to" in novas:
            for leave, vals in zip(self, valores, strict=False):
                if (
                    leave.l10n_br_aviso_ferias_data
                    and leave.l10n_br_aviso_ferias_inicio
                    <= novas["request_date_from"]
                    <= novas["request_date_to"]
                    <= leave.l10n_br_aviso_ferias_fim
                ):
                    vals.update(
                        {
                            "l10n_br_aviso_ferias_data": leave.l10n_br_aviso_ferias_data,
                            "l10n_br_aviso_ferias_inicio": leave.l10n_br_aviso_ferias_inicio,
                            "l10n_br_aviso_ferias_fim": leave.l10n_br_aviso_ferias_fim,
                        }
                    )
        return valores
