# Copyright 2026 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class HrPayslipDataAviso(models.Model):
    """Data da concessão do aviso prévio na rescisão (``dtAvPrv`` do S-2299).

    Mantido em arquivo próprio: é só o campo e a conferência da data, sem
    relação com o cálculo das verbas da rescisão.
    """

    _inherit = "hr.payslip"

    l10n_br_data_aviso_previo = fields.Date(
        string="Data da Concessão do Aviso Prévio",
        copy=False,
        help="Data em que o aviso prévio foi dado ao empregado (indenizado ou "
        "trabalhado). Opcional: com ela, o S-2299 informa dtAvPrv. Não pode ser "
        "anterior à admissão nem posterior ao fim da rescisão.",
    )

    @api.constrains("l10n_br_data_aviso_previo", "date_to", "contract_id")
    def _check_l10n_br_data_aviso_previo(self):
        for rec in self:
            data = rec.l10n_br_data_aviso_previo
            if not data:
                continue
            admissao = rec.contract_id.date_start
            if (rec.date_to and data > rec.date_to) or (admissao and data < admissao):
                raise ValidationError(
                    _(
                        "A Data da Concessão do Aviso Prévio (%(data)s) deve estar "
                        "entre a admissão (%(adm)s) e o fim da rescisão "
                        "(%(fim)s)."
                    )
                    % {"data": data, "adm": admissao, "fim": rec.date_to}
                )
