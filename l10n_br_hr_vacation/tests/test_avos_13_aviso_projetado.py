# Copyright 2024 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""
Testes: avos do 13º na rescisão com aviso indenizado que cruza o ano.

Súmula 371 TST: o aviso indenizado projeta o contrato. Cada ano-base tem o seu
13º (Lei 4.090/62): o ano do desligamento vai até 31/12 e o ano projetado conta
de 1º/01 até a data projetada, com a regra dos 15 dias em cada um.

TG-136: ``DECIMO_RESCISAO`` paga só os avos do 13º proporcional (até a data do
desligamento) e ``DECIMO_AVISO_INDENIZADO`` os que o aviso projeta; INSS, IRRF e
FGTS do 13º seguem sobre o total das duas.
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

    def _total_13(self, payslip):
        return self._get_line_total(payslip, "DECIMO_RESCISAO") + self._get_line_total(
            payslip, "DECIMO_AVISO_INDENIZADO"
        )

    def test_projecao_com_menos_de_15_dias_no_ano_seguinte(self):
        """30/11/2026 + 33 dias = 02/01/2027: 12 avos de 2026 e 0 de 2027.

        Antes só o ano da data projetada era medido (2 dias de janeiro -> 0
        avo) e o 13º saía zerado.
        """
        payslip = self._rescisao(date(2025, 7, 1), date(2026, 11, 30))
        self.assertEqual(payslip._l10n_br_data_projetada_rescisao(), date(2027, 1, 2))
        self.assertEqual(payslip.l10n_br_avos_13, 12)
        # 11 avos até 30/11 (proporcional) + 1 do aviso (dezembro).
        self.assertEqual(payslip.l10n_br_avos_13_proporcional, 11)
        self.assertEqual(payslip.l10n_br_avos_13_aviso, 1)
        self.assertAlmostEqualMoney(
            self._get_line_total(payslip, "DECIMO_RESCISAO"), 1833.33
        )
        self.assertAlmostEqualMoney(
            self._get_line_total(payslip, "DECIMO_AVISO_INDENIZADO"), 166.67
        )
        self.assertAlmostEqualMoney(self._total_13(payslip), 2000.00)
        self.assertGreater(self._get_line_total(payslip, "INSS_13"), 0)
        self.assertGreater(self._get_line_total(payslip, "FGTS_13"), 0)

    def test_projecao_com_15_dias_ou_mais_no_ano_seguinte(self):
        """20/12/2026 + 33 dias = 22/01/2027: 12 avos de 2026 + 1 de 2027."""
        payslip = self._rescisao(date(2025, 7, 1), date(2026, 12, 20))
        self.assertEqual(payslip._l10n_br_data_projetada_rescisao(), date(2027, 1, 22))
        self.assertEqual(payslip.l10n_br_avos_13, 13)
        self.assertAlmostEqualMoney(self._total_13(payslip), 2166.67)

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
        # Sem aviso indenizado não há rubrica do 13º sobre o aviso.
        self.assertEqual(payslip.l10n_br_avos_13_aviso, 0)
        self.assertFalse(
            payslip.line_ids.filtered(lambda ln: ln.code == "DECIMO_AVISO_INDENIZADO")
        )

    def test_projecao_dentro_do_mesmo_ano_nao_regride(self):
        """Aviso que não cruza o ano segue medido só no ano do desligamento."""
        payslip = self._rescisao(date(2025, 7, 1), date(2026, 8, 20))
        self.assertEqual(payslip._l10n_br_data_projetada_rescisao(), date(2026, 9, 22))
        self.assertEqual(payslip.l10n_br_avos_13, 9)

    def test_aviso_cruzando_o_ano_com_15_dias_em_janeiro(self):
        """Exemplo da story: dispensa em 13/12/2026, aviso até 15/01/2027.

        13 avos no total (2.166,67): 11 de proporcional (dezembro só tem 13
        dias) e 2 do aviso (dezembro e os 15 dias de janeiro).
        """
        payslip = self._rescisao(date(2025, 7, 1), date(2026, 12, 13))
        self.assertEqual(payslip._l10n_br_data_projetada_rescisao(), date(2027, 1, 15))
        self.assertEqual(payslip.l10n_br_avos_13, 13)
        self.assertEqual(payslip.l10n_br_avos_13_proporcional, 11)
        self.assertEqual(payslip.l10n_br_avos_13_aviso, 2)
        self.assertAlmostEqualMoney(
            self._get_line_total(payslip, "DECIMO_RESCISAO"), 1833.34
        )
        self.assertAlmostEqualMoney(
            self._get_line_total(payslip, "DECIMO_AVISO_INDENIZADO"), 333.33
        )
        self.assertAlmostEqualMoney(self._total_13(payslip), 2166.67)
        # Os encargos do 13º recaem sobre o total das duas rubricas.
        self.assertAlmostEqualMoney(self._get_line_total(payslip, "FGTS_13"), 173.33)

    def test_aviso_cruzando_o_ano_com_14_dias_em_janeiro(self):
        """Dispensa em 12/12/2026, aviso até 14/01/2027: janeiro não gera avo."""
        payslip = self._rescisao(date(2025, 7, 1), date(2026, 12, 12))
        self.assertEqual(payslip._l10n_br_data_projetada_rescisao(), date(2027, 1, 14))
        self.assertEqual(payslip.l10n_br_avos_13_proporcional, 11)
        self.assertEqual(payslip.l10n_br_avos_13_aviso, 1)
        self.assertAlmostEqualMoney(
            self._get_line_total(payslip, "DECIMO_RESCISAO"), 1833.33
        )
        self.assertAlmostEqualMoney(
            self._get_line_total(payslip, "DECIMO_AVISO_INDENIZADO"), 166.67
        )
        self.assertAlmostEqualMoney(self._total_13(payslip), 2000.00)

    def test_aviso_de_90_dias_com_dispensa_em_31_12(self):
        """Exemplo da story: aviso de 90 dias (20 anos de casa), dispensa em 31/12.

        15 avos no total (2.500,00): 12 de proporcional (2.000,00) e 3 do aviso
        (janeiro a março de 2027, 500,00). A rubrica do aviso passa de 12/12
        sem que o proporcional passe.
        """
        payslip = self._rescisao(date(2006, 1, 1), date(2026, 12, 31))
        self.assertEqual(payslip._l10n_br_dias_aviso_previo(), 90)
        self.assertEqual(payslip._l10n_br_data_projetada_rescisao(), date(2027, 3, 31))
        self.assertEqual(payslip.l10n_br_avos_13_proporcional, 12)
        self.assertEqual(payslip.l10n_br_avos_13_aviso, 3)
        self.assertAlmostEqualMoney(
            self._get_line_total(payslip, "DECIMO_RESCISAO"), 2000.00
        )
        self.assertAlmostEqualMoney(
            self._get_line_total(payslip, "DECIMO_AVISO_INDENIZADO"), 500.00
        )
        self.assertAlmostEqualMoney(self._total_13(payslip), 2500.00)
        self.assertAlmostEqualMoney(self._get_line_total(payslip, "FGTS_13"), 200.00)

    def test_liquido_soma_as_duas_rubricas(self):
        """O líquido inclui o 13º do aviso: bruto das duas menos os encargos."""
        payslip = self._rescisao(date(2006, 1, 1), date(2026, 12, 31))
        esperado = (
            self._get_line_total(payslip, "SALDO_SALARIO")
            + self._get_line_total(payslip, "DECIMO_RESCISAO")
            + self._get_line_total(payslip, "DECIMO_AVISO_INDENIZADO")
            + self._get_line_total(payslip, "AVISO_PREVIO_INDENIZADO")
            + self._get_line_total(payslip, "FERIAS_INDENIZADAS")
            + self._get_line_total(payslip, "ADICIONAL_FERIAS_INDENIZADAS")
            + self._get_line_total(payslip, "FERIAS_VENCIDAS")
            + self._get_line_total(payslip, "ADICIONAL_FERIAS_VENCIDAS")
            - self._get_line_total(payslip, "INSS")
            - self._get_line_total(payslip, "INSS_13")
            - self._get_line_total(payslip, "IRRF")
            - self._get_line_total(payslip, "IRRF_13")
        )
        self.assertAlmostEqualMoney(self._get_line_total(payslip, "NET"), esperado)

    def test_centavo_de_arredondamento_fica_no_proporcional(self):
        """Cada rubrica pelos próprios avos; o centavo sobra no proporcional.

        Salário 5.000,00, desligamento em 31/10 com 33 dias de aviso (03/12):
        10 avos de proporcional + 1 do aviso. O aviso é 5.000,00 / 12 = 416,67
        e o proporcional é o total (4.583,33) menos isso: 4.166,66.
        """
        payslip = self._rescisao(date(2025, 7, 1), date(2026, 10, 31), wage=5000.00)
        self.assertEqual(payslip.l10n_br_avos_13_proporcional, 10)
        self.assertEqual(payslip.l10n_br_avos_13_aviso, 1)
        self.assertAlmostEqualMoney(
            self._get_line_total(payslip, "DECIMO_AVISO_INDENIZADO"), 416.67
        )
        self.assertAlmostEqualMoney(
            self._get_line_total(payslip, "DECIMO_RESCISAO"), 4166.66
        )
        self.assertAlmostEqualMoney(self._total_13(payslip), 4583.33)
