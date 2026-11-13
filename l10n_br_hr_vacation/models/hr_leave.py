# Copyright 2026 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from collections import defaultdict
from datetime import date

from dateutil.relativedelta import relativedelta

from odoo import _, models
from odoo.exceptions import ValidationError


class HrLeave(models.Model):
    _inherit = "hr.leave"

    def _check_validity(self):
        """Férias valem contra a alocação até o fim do período concessivo.

        O ``hr_holidays`` só aceita a ausência dentro de ``date_from`` e
        ``date_to`` da alocação, e aqui ``date_to`` é o fim do período
        aquisitivo. Mas as férias do período aquisitivo são gozadas nos 12
        meses seguintes (CLT art. 134), depois de a alocação vencer. As
        ausências de férias passam por ``_l10n_br_check_ferias_concessivo``;
        as dos demais tipos seguem o padrão.
        """
        vacation_type = self.env.ref(
            "l10n_br_hr_vacation.leave_type_ferias", raise_if_not_found=False
        )
        ferias = self.filtered(
            lambda leave: vacation_type and leave.holiday_status_id == vacation_type
        )
        res = super(HrLeave, self - ferias)._check_validity()
        if ferias:
            ferias._l10n_br_check_ferias_concessivo()
        return res

    def _l10n_br_check_ferias_concessivo(self):
        """Cada ausência consome o saldo da alocação mais antiga que cobre o
        seu início, do aquisitivo até o fim do concessivo.

        O saldo continua sendo o dos dias de direito da alocação: o
        concessivo estende a validade, não o direito. Depois do concessivo as
        férias são devidas em dobro (CLT art. 137) e a ausência não é aceita
        por este saldo.
        """
        vacation_type = self.holiday_status_id[:1]
        if vacation_type.requires_allocation == "no":
            return
        Allocation = self.env["hr.leave.allocation"].with_context(active_test=False)
        for employee in self.employee_id:
            saldo = {
                alloc: alloc.number_of_days
                for alloc in Allocation.search(
                    [
                        ("employee_id", "=", employee.id),
                        ("holiday_status_id", "=", vacation_type.id),
                        ("state", "=", "validate"),
                    ]
                ).sorted(lambda alloc: (alloc.date_to or alloc.date_from, alloc.id))
            }
            todas = self.env["hr.leave"].search(
                [
                    ("employee_id", "=", employee.id),
                    ("holiday_status_id", "=", vacation_type.id),
                    ("state", "in", ["confirm", "validate1", "validate"]),
                ]
            )
            a_validar = todas | self.filtered(
                lambda leave: leave.employee_id == employee
            )
            restante = defaultdict(float)
            for leave in a_validar.sorted(lambda leave: (leave.date_from, leave.id)):
                inicio = leave.date_from.date()
                cobrindo = [
                    alloc
                    for alloc in saldo
                    if alloc.date_from <= inicio <= self._l10n_br_fim_concessivo(alloc)
                ]
                if not cobrindo and leave in self:
                    raise ValidationError(
                        _(
                            "You do not have any allocation for this time off type.\n"
                            "Please request an allocation before submitting your "
                            "time off request."
                        )
                    )
                falta = leave.number_of_days
                for alloc in cobrindo:
                    usado = min(falta, saldo[alloc])
                    saldo[alloc] -= usado
                    falta -= usado
                    if not falta:
                        break
                if round(falta, 2) > 0:
                    restante[leave] = falta
            if any(leave in self for leave in restante):
                raise ValidationError(
                    _("There is no valid allocation to cover that request.")
                )

    @staticmethod
    def _l10n_br_fim_concessivo(alloc):
        """Último dia em que a alocação cobre férias: o fim do período
        concessivo (12 meses depois do aquisitivo, CLT art. 134). Sem
        ``date_to`` a alocação não vence."""
        if not alloc.date_to:
            return date.max
        return alloc.date_to + relativedelta(years=1)
