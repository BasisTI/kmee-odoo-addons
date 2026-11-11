# Copyright 2024 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


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

    @api.constrains("payslip_id", "date")
    def _check_datas_ate_faltas(self):
        """Falta criada direto no modelo não fura "datas <= faltas" do holerite."""
        for slip in self.payslip_id:
            if len(slip.l10n_br_falta_ids) > slip.l10n_br_faltas_injustificadas:
                raise ValidationError(
                    _(
                        "Há %(datas)s datas de falta para %(faltas)s faltas "
                        "injustificadas no holerite.",
                        datas=len(slip.l10n_br_falta_ids),
                        faltas=slip.l10n_br_faltas_injustificadas,
                    )
                )

    # O que cada holerite do empregado desconta de DSR depende das faltas dos
    # outros (semana que atravessa o mês): a reconciliação é o ponto único do
    # hr.payslip (``_l10n_br_dsr_reconciliar``), aqui só se tira o "antes".

    @api.model
    def _l10n_br_exigir_aberto(self, slips):
        if self.env.context.get("l10n_br_dsr_reconciliando"):
            return
        fechados = slips.filtered(lambda r: r.state not in ("draft", "verify"))
        if fechados:
            raise UserError(
                _(
                    "Não é possível lançar, alterar ou apagar falta de holerite "
                    "já confirmado ou cancelado: %(fechados)s. Volte-o para "
                    "rascunho primeiro.",
                    fechados=", ".join(fechados.mapped(lambda r: r.number or r.name)),
                )
            )

    def _l10n_br_com_reconciliacao(self, operacao, slips=None):
        """Roda ``operacao`` e reconcilia o DSR dos outros holerites."""
        Payslip = self.env["hr.payslip"]
        if self.env.context.get("l10n_br_dsr_reconciliando"):
            return operacao()
        slips = slips if slips is not None else self.payslip_id
        empregados = slips.employee_id
        antes = Payslip._l10n_br_dsr_participacao(empregados)
        res = operacao()
        Payslip._l10n_br_dsr_reconciliar(antes, empregados, slips.exists())
        return res

    @api.model_create_multi
    def create(self, vals_list):
        slips = self.env["hr.payslip"].browse(
            [v["payslip_id"] for v in vals_list if v.get("payslip_id")]
        )
        self._l10n_br_exigir_aberto(slips)
        return self._l10n_br_com_reconciliacao(
            lambda: super(HrPayslipFalta, self).create(vals_list), slips
        )

    def write(self, vals):
        if not {"date", "payslip_id"} & set(vals):
            return super().write(vals)
        self._l10n_br_exigir_aberto(self.payslip_id)
        slips = self.payslip_id | self.env["hr.payslip"].browse(
            [vals["payslip_id"]] if vals.get("payslip_id") else []
        )
        return self._l10n_br_com_reconciliacao(
            lambda: super(HrPayslipFalta, self).write(vals), slips
        )

    def unlink(self):
        self._l10n_br_exigir_aberto(self.payslip_id)
        slips = self.payslip_id
        return self._l10n_br_com_reconciliacao(
            lambda: super(HrPayslipFalta, self).unlink(), slips
        )
