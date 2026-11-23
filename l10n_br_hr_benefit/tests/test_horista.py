# Copyright 2026 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""TG-166: o horista tem o vale-transporte pelo mensal de referência do contrato."""

from .test_beneficios import TestValeTransporteDiario


class TestHoristaVT(TestValeTransporteDiario):
    def test_desc_vt_do_horista(self):
        emp, contract = self._contrato(wage=3500.0, diario=10.0)
        contract.write({"l10n_br_unidade_salario": "hora", "l10n_br_valor_hora": 20.0})
        # o Salário do horista é o mensal de referência (valor da hora × divisor)
        self.assertGreater(contract.wage, 3500.0)
        payslip = self._create_payslip_benefit(emp, contract)
        payslip.l10n_br_horas_pagas = 176.0
        payslip.compute_sheet()
        # 6% do mensal de referência passa do crédito (210): desconta o crédito
        self.assertAlmostEqualMoney(self._get_line_total(payslip, "VT_INFO"), 210.0)
        self.assertAlmostEqualMoney(self._get_line_total(payslip, "DESC_VT"), 210.0)
