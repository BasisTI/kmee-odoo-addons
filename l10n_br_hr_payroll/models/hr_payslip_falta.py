# Copyright 2024 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class HrPayslipFalta(models.Model):
    """Dia de falta injustificada de um holerite.

    Serve para descontar o DSR da semana em que a falta ocorreu (Lei 605/49,
    art. 6º). O total de faltas que desconta o salário continua em
    ``hr.payslip.l10n_br_faltas_injustificadas``.
    """

    _name = "l10n_br.hr.payslip.falta"
    _description = "Falta injustificada do holerite"
    _order = "date"

    payslip_id = fields.Many2one(
        "hr.payslip",
        string="Holerite",
        required=True,
        ondelete="cascade",
        index=True,
    )
    date = fields.Date(string="Data da falta", required=True)

    _sql_constraints = [
        (
            "payslip_date_uniq",
            "unique(payslip_id, date)",
            "A mesma falta não pode ser lançada duas vezes no holerite.",
        ),
    ]

    @api.constrains("date", "payslip_id")
    def _check_date_no_periodo(self):
        for rec in self:
            slip = rec.payslip_id
            if slip.date_from and slip.date_to:
                if not slip.date_from <= rec.date <= slip.date_to:
                    raise ValidationError(
                        _(
                            "A falta de %(dia)s está fora do período do holerite "
                            "(%(ini)s a %(fim)s).",
                            dia=rec.date,
                            ini=slip.date_from,
                            fim=slip.date_to,
                        )
                    )
