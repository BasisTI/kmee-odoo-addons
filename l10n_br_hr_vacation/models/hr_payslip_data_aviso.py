# Copyright 2026 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


# Arquivo separado de propósito (rebase com a TG-136, que mexe em hr_payslip.py).
class HrPayslipDataAviso(
    models.Model
):  # pylint: disable=consider-merging-classes-inherited
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

    def write(self, vals):
        """A data só muda com a rescisão aberta (rascunho ou verificação).

        Confirmada, a data já saiu no TRCT e pode ter ido ao S-2299 (``dtAvPrv``):
        mudá-la deixaria o holerite divergente do que foi declarado. Volte o
        holerite para rascunho antes, como nos demais campos que mudam o cálculo.
        """
        if "l10n_br_data_aviso_previo" in vals:
            fechados = self.filtered(lambda r: r.state not in ("draft", "verify"))
            if fechados:
                raise UserError(
                    _(
                        "A Data da Concessão do Aviso Prévio só pode ser alterada "
                        "com a rescisão em rascunho ou em verificação: "
                        "%(fechados)s já está confirmado. Volte-o para rascunho "
                        "primeiro.",
                        fechados=", ".join(
                            fechados.mapped(lambda r: r.number or r.name)
                        ),
                    )
                )
        return super().write(vals)

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
