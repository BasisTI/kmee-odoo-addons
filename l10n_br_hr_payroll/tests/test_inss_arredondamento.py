# Copyright 2026 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""TG-158: o INSS progressivo trunca cada faixa em centavos (sem erro de float).

Antes, o total era arredondado com ROUND_HALF_UP e ficava centavos acima do
cálculo da folha de referência. A base é quantizada em centavos antes das
faixas. Faixas da tabela vigente do módulo (2026) e um caso de 2025.
"""
from datetime import date

from odoo.tests.common import BaseCase

from odoo.addons.l10n_br_hr_payroll.models.salary_rules_br import calc_inss

from .common import PayrollCommon

# (teto, alíquota) — l10n_br.hr.payroll.inss.faixa.csv
FAIXAS_2026 = [
    (1621.00, 0.075),
    (2902.84, 0.09),
    (4354.27, 0.12),
    (8475.55, 0.14),
]
TABELA_2025 = [
    (1518.00, 0.075),
    (2793.88, 0.09),
    (4190.83, 0.12),
    (8157.41, 0.14),
]


class TestInssTruncado(BaseCase):
    def _inss(self, base):
        return calc_inss(base, FAIXAS_2026)

    def test_base_em_cada_faixa(self):
        for base, esperado in [
            (1000.00, 75.00),
            (2000.00, 155.68),
            (3000.00, 248.58),
            (5000.00, 501.50),
        ]:
            self.assertEqual(self._inss(base), esperado, base)

    def test_limites_exatos_das_faixas(self):
        for base, esperado in [
            (1621.00, 121.57),
            (1621.01, 121.57),
            (2902.84, 236.93),
            (2902.85, 236.93),
            (4354.27, 411.10),
            (4354.28, 411.10),
            (8475.55, 988.07),
        ]:
            self.assertEqual(self._inss(base), esperado, base)

    def test_teto(self):
        for base in (8475.56, 10000.00, 50000.00):
            self.assertEqual(self._inss(base), 988.07, base)

    def test_zero_e_negativo(self):
        self.assertEqual(self._inss(0), 0.0)
        self.assertEqual(self._inss(-10), 0.0)

    def test_diferenca_de_centavos_antes_depois(self):
        """3.000,00: faixas 121,575 + 115,2156 + 11,7932. Antes 248,60; agora 248,58."""
        self.assertEqual(self._inss(1621.00), 121.57)  # 121,575 exato
        self.assertEqual(self._inss(3000.00), 248.58)

    def test_tabela_2025(self):
        # 3.000,00 na tabela de 2025
        self.assertEqual(calc_inss(3000.00, TABELA_2025), 253.40)
        self.assertEqual(calc_inss(8157.41, TABELA_2025), 951.62)

    def test_teto_2024_e_885(self):
        """Teto oficial de 2024: R$ 908,85 (o código antigo dava 908,86)."""
        h = [(1412.00, 0.075), (2666.68, 0.09), (4000.03, 0.12), (7786.02, 0.14)]
        self.assertEqual(calc_inss(7786.02, h), 908.85)

    def test_base_com_ruido_de_float_de_subtracao(self):
        """Base montada por subtração (GROSS - FALTAS - DESC_DSR) não perde centavo."""
        base = 1622.30 - 108.15 - 108.15
        self.assertNotEqual(base, 1406.00)  # ruído de float
        self.assertEqual(self._inss(base), 105.45)
        self.assertEqual(self._inss(1406.00), 105.45)
        base = 5000.11 - 166.67 - 166.67
        self.assertEqual(self._inss(base), 454.85)

    def test_sem_erro_de_float_em_meio_centavo(self):
        self.assertEqual(calc_inss(1.15, [(1000.00, 0.0075)]), 0.0)
        self.assertEqual(calc_inss(1000.00, [(1000.00, 0.0075)]), 7.5)
        self.assertEqual(calc_inss(1234.56, [(2000.00, 0.01)]), 12.34)


class TestInssHoleriteComFaltas(PayrollCommon):
    """A base do INSS vem de GROSS - FALTAS - DESC_DSR (float com ruído)."""

    def _inss_com_faltas(self, wage, faltas):
        emp = self._create_employee()
        contract = self._create_contract(emp, wage=wage)
        payslip = self._create_payslip(
            emp, contract, date_from=date(2026, 3, 1), date_to=date(2026, 3, 31)
        )
        payslip.write({"l10n_br_faltas_injustificadas": faltas})
        payslip.compute_sheet()
        return self._get_line_total(payslip, "INSS")

    def test_faixa_2_com_duas_faltas(self):
        self.assertEqual(self._inss_com_faltas(1622.30, 2), 105.45)

    def test_faixa_4_com_uma_falta(self):
        self.assertEqual(self._inss_com_faltas(5000.11, 1), 454.85)
