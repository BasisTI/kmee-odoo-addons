# Copyright 2024 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

from . import salary_rules_br


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

    # Semana que atravessa a virada do mês: o repouso é descontado uma vez só,
    # no holerite que traz a primeira falta dela (``_l10n_br_semanas_com_falta``).
    # Logo, lançar, mudar ou apagar uma falta pode mudar o DESC_DSR de OUTRO
    # holerite do empregado; a reconciliação fica aqui, no ponto de gravação.

    @api.model
    def _l10n_br_reconciliar_semanas(self, pares):
        """Recalcula os holerites que dependem da primeira falta de cada semana.

        Args:
            pares: ``(holerite, empregado, dia)`` das faltas que mudaram.
        """
        afetados = self.env["hr.payslip"]
        for slip, empregado, dia in pares:
            inicio = salary_rules_br.inicio_semana(dia)
            outras = self.search(
                [
                    ("payslip_id", "!=", slip.id),
                    ("payslip_id.employee_id", "=", empregado.id),
                    ("payslip_id.state", "!=", "cancel"),
                    ("date", ">=", inicio),
                    ("date", "<=", inicio + timedelta(days=6)),
                ]
            )
            for outro in outras.mapped("payslip_id"):
                primeira = min(
                    outras.filtered(lambda f: f.payslip_id == outro).mapped("date")
                )
                if primeira >= dia:
                    afetados |= outro
        fechados = afetados.filtered(lambda r: r.state not in ("draft", "verify"))
        if fechados:
            raise UserError(
                _(
                    "Não é possível alterar esta falta: %(fechados)s, do mesmo "
                    "empregado, já está confirmado e o desconto de DSR da semana "
                    "depende dela. Volte o confirmado para rascunho primeiro.",
                    fechados=", ".join(fechados.mapped(lambda r: r.number or r.name)),
                )
            )
        afetados.compute_sheet()

    def _l10n_br_pares(self):
        return [(f.payslip_id, f.payslip_id.employee_id, f.date) for f in self]

    @api.model_create_multi
    def create(self, vals_list):
        faltas = super().create(vals_list)
        self._l10n_br_reconciliar_semanas(faltas._l10n_br_pares())
        return faltas

    def write(self, vals):
        if not {"date", "payslip_id"} & set(vals):
            return super().write(vals)
        pares = self._l10n_br_pares()
        res = super().write(vals)
        self._l10n_br_reconciliar_semanas(pares + self._l10n_br_pares())
        return res

    def unlink(self):
        pares = self._l10n_br_pares()
        res = super().unlink()
        self._l10n_br_reconciliar_semanas(pares)
        return res
