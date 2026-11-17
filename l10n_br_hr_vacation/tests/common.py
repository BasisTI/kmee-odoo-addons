# Copyright 2024 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""
Classe base com fixtures para testes de férias e 13º salário.
"""
from unittest.mock import patch

from odoo.addons.l10n_br_hr_payroll.tests.common import PayrollCommon


class VacationCommon(PayrollCommon):
    """Classe base para testes do módulo l10n_br_hr_vacation."""

    # TG-147: a rescisão recusa o cálculo sem a alocação do último período
    # aquisitivo. Os demais testes não montam alocações e testam outra coisa:
    # a exigência fica desligada neles; só os testes dela a ligam.
    exigir_alocacao_periodo = False

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        if not cls.exigir_alocacao_periodo:
            patcher = patch.object(
                type(cls.env["hr.payslip"]),
                "_l10n_br_exigir_alocacao_periodo_completo",
                lambda self: None,
            )
            patcher.start()
            cls.addClassCleanup(patcher.stop)
        cls.structure_ferias = cls.env.ref("l10n_br_hr_vacation.structure_ferias")
        cls.structure_13_primeira = cls.env.ref(
            "l10n_br_hr_vacation.structure_13_primeira_parcela"
        )
        cls.structure_13_segunda = cls.env.ref(
            "l10n_br_hr_vacation.structure_13_segunda_parcela"
        )
        cls.structure_13 = cls.env.ref("l10n_br_hr_vacation.structure_13")
        cls.structure_rescisao = cls.env.ref("l10n_br_hr_vacation.structure_rescisao")
        cls.leave_type_ferias = cls.env.ref("l10n_br_hr_vacation.leave_type_ferias")
