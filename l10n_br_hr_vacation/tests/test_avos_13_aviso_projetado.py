# Copyright 2024 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""
Testes: avos do 13º na rescisão com aviso indenizado que cruza o ano.

Súmula 371 TST: o aviso indenizado projeta o contrato. Cada ano-base tem o seu
13º (Lei 4.090/62): o ano do desligamento vai até 31/12 e o ano projetado conta
de 1º/01 até a data projetada, com a regra dos 15 dias em cada um.
"""
from datetime import date

from odoo.tests import tagged

from .common import VacationCommon


@tagged("post_install", "-at_install")
class TestAvos13AvisoProjetado(VacationCommon):
    def _rescisao(self, date_start, date_to, aviso="indenizado", wage=2000.00):
        emp = self._create_employee()
        contract = self._create_contract(emp, wage=wage, date_start=date_start)
        payslip = self.env["hr.payslip"].create(
            {
                "name": f"Rescisão {date_to}",
                "employee_id": emp.id,
                "contract_id": contract.id,
                "struct_id": self.structure_rescisao.id,
                "date_from": date_to.replace(day=1),
                "date_to": date_to,
                "l10n_br_tipo_rescisao": "sem_justa_causa",
                "l10n_br_aviso_previo": aviso,
                "company_id": self.env.company.id,
            }
        )
        payslip.compute_sheet()
        return payslip

    def test_projecao_com_menos_de_15_dias_no_ano_seguinte(self):
        """30/11/2026 + 33 dias = 02/01/2027: 12 avos de 2026 e 0 de 2027.

        Antes só o ano da data projetada era medido (2 dias de janeiro -> 0
        avo) e o 13º saía zerado.
        """
        payslip = self._rescisao(date(2025, 7, 1), date(2026, 11, 30))
        self.assertEqual(
            payslip._l10n_br_data_projetada_rescisao(), date(2027, 1, 2)
        )
        self.assertEqual(payslip.l10n_br_avos_13, 12)
        self.assertAlmostEqualMoney(
            self._get_line_total(payslip, "DECIMO_RESCISAO"), 2000.00
        )
        self.assertGreater(self._get_line_total(payslip, "INSS_13"), 0)
        self.assertGreater(self._get_line_total(payslip, "FGTS_13"), 0)

    def test_projecao_com_15_dias_ou_mais_no_ano_seguinte(self):
        """20/12/2026 + 33 dias = 22/01/2027: 12 avos de 2026 + 1 de 2027."""
        payslip = self._rescisao(date(2025, 7, 1), date(2026, 12, 20))
        self.assertEqual(
            payslip._l10n_br_data_projetada_rescisao(), date(2027, 1, 22)
        )
        self.assertEqual(payslip.l10n_br_avos_13, 13)
        self.assertAlmostEqualMoney(
            self._get_line_total(payslip, "DECIMO_RESCISAO"), 2166.67
        )

    def test_sem_aviso_indenizado_nao_projeta(self):
        """Aviso trabalhado: só o ano do desligamento (30/11 -> 11 avos)."""
        payslip = self._rescisao(
            date(2025, 7, 1), date(2026, 11, 30), aviso="trabalhado"
        )
        self.assertEqual(payslip.l10n_br_avos_13, 11)
        payslip = self._rescisao(
            date(2025, 7, 1), date(2026, 11, 10), aviso="trabalhado"
        )
        self.assertEqual(payslip.l10n_br_avos_13, 10)

    def test_projecao_dentro_do_mesmo_ano_nao_regride(self):
        """Aviso que não cruza o ano segue medido só no ano do desligamento."""
        payslip = self._rescisao(date(2025, 7, 1), date(2026, 8, 20))
        self.assertEqual(
            payslip._l10n_br_data_projetada_rescisao(), date(2026, 9, 22)
        )
        self.assertEqual(payslip.l10n_br_avos_13, 9)
