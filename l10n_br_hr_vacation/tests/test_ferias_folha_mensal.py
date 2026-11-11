# Copyright 2024 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""Folha mensal sem os dias de férias já pagos no recibo (TG-83).

Casos de referência: gabarito da POC, M01 (10 dias de férias no meio de
11/2026) e M02 (mês inteiro em férias), CLT arts. 129 e 145.
"""
from datetime import date

from odoo.tests import tagged

from .common import VacationCommon

NOV_INI, NOV_FIM = date(2026, 11, 1), date(2026, 11, 30)
DEZ_INI, DEZ_FIM = date(2026, 12, 1), date(2026, 12, 31)


@tagged("post_install", "-at_install")
class TestFeriasFolhaMensal(VacationCommon):
    def _contrato(self, wage=3600.0):
        emp = self._create_employee()
        return emp, self._create_contract(emp, wage=wage, date_start=date(2024, 1, 2))

    def _alocacao(self, emp):
        alloc = self.env["hr.leave.allocation"].create(
            {
                "employee_id": emp.id,
                "holiday_status_id": self.leave_type_ferias.id,
                "date_from": date(2025, 1, 2),
                "date_to": date(2026, 1, 1),
            }
        )
        alloc.action_validate()
        return alloc

    def _recibo(self, emp, contract, inicio, fim, dias_gozo, dias_abono=0):
        return self.env["hr.payslip"].create(
            {
                "name": "Férias %s" % inicio,
                "employee_id": emp.id,
                "contract_id": contract.id,
                "struct_id": self.structure_ferias.id,
                "date_from": inicio,
                "date_to": fim,
                "l10n_br_ferias_allocation_id": self._alocacao(emp).id,
                "l10n_br_dias_periodo_gozado": dias_gozo,
                "l10n_br_dias_abono": dias_abono,
                "company_id": self.env.company.id,
            }
        )

    def _salario(self, emp, contract, inicio, fim):
        slip = self._create_payslip(emp, contract, inicio, fim)
        return self._get_line_total(slip, "SALARIO_BASE")

    def test_sem_ferias_paga_o_mes_cheio(self):
        emp, contract = self._contrato()
        self.assertAlmostEqualMoney(
            self._salario(emp, contract, NOV_INI, NOV_FIM), 3600
        )

    def test_10_dias_de_ferias_no_meio_do_mes(self):
        """M01: 3.600 x 20/30 = 2.400, não 3.600."""
        emp, contract = self._contrato()
        self._recibo(emp, contract, date(2026, 11, 16), date(2026, 11, 25), 10)
        self.assertAlmostEqualMoney(
            self._salario(emp, contract, NOV_INI, NOV_FIM), 2400
        )

    def test_mes_inteiro_em_ferias(self):
        """M02: nada de salário no mês."""
        emp, contract = self._contrato(4000.0)
        self._recibo(emp, contract, NOV_INI, NOV_FIM, 30)
        self.assertAlmostEqualMoney(self._salario(emp, contract, NOV_INI, NOV_FIM), 0)

    def test_ferias_atravessando_dois_meses(self):
        """Férias de 20/11 a 09/12: 19 dias em novembro, 21 em dezembro."""
        emp, contract = self._contrato(3000.0)
        self._recibo(emp, contract, date(2026, 11, 20), date(2026, 12, 9), 20)
        self.assertAlmostEqualMoney(
            self._salario(emp, contract, NOV_INI, NOV_FIM), 1900
        )
        self.assertAlmostEqualMoney(
            self._salario(emp, contract, DEZ_INI, DEZ_FIM), 2100
        )

    def test_abono_pecuniario_nao_desconta_dias(self):
        """20 dias gozados e 10 vendidos: só os 20 dias gozados saem do salário."""
        emp, contract = self._contrato(3000.0)
        self._recibo(emp, contract, NOV_INI, date(2026, 11, 20), 20, dias_abono=10)
        self.assertAlmostEqualMoney(
            self._salario(emp, contract, NOV_INI, NOV_FIM), 1000
        )

    def test_recibo_cancelado_nao_desconta(self):
        emp, contract = self._contrato()
        recibo = self._recibo(emp, contract, date(2026, 11, 16), date(2026, 11, 25), 10)
        recibo.action_payslip_cancel()
        self.assertAlmostEqualMoney(
            self._salario(emp, contract, NOV_INI, NOV_FIM), 3600
        )

    def test_recibo_de_outro_contrato_nao_desconta(self):
        emp, contract = self._contrato()
        outro, contrato_outro = self._contrato()
        self._recibo(outro, contrato_outro, date(2026, 11, 16), date(2026, 11, 25), 10)
        self.assertAlmostEqualMoney(
            self._salario(emp, contract, NOV_INI, NOV_FIM), 3600
        )

    def test_periculosidade_acompanha_os_dias_fora_das_ferias(self):
        emp, contract = self._contrato(3000.0)
        contract.l10n_br_periculosidade = True
        self._recibo(emp, contract, NOV_INI, date(2026, 11, 15), 15)
        slip = self._create_payslip(emp, contract, NOV_INI, NOV_FIM)
        self.assertAlmostEqualMoney(
            self._get_line_total(slip, "ADICIONAL_PERICULOSIDADE"), 450
        )

    def _inss(self, slip):
        return self._get_line_total(slip, "INSS")

    def test_inss_do_mensal_apurado_na_competencia(self):
        """M01: INSS sobre mensal + férias (4.000), menos o retido no recibo.

        Férias de 10 dias: 1.200 + 1/3 = 1.600, INSS retido 120,00. Sobre a
        soma de 4.000 o INSS é 368,60, então o mensal retém 248,60.
        """
        emp, contract = self._contrato(3600.0)
        recibo = self._recibo(emp, contract, date(2026, 11, 16), date(2026, 11, 25), 10)
        recibo.compute_sheet()
        mensal = self._create_payslip(emp, contract, NOV_INI, NOV_FIM)
        self.assertAlmostEqualMoney(self._get_line_total(recibo, "GROSS"), 1600)
        self.assertAlmostEqualMoney(self._inss(recibo), 120)
        self.assertAlmostEqualMoney(self._inss(mensal), 248.60)
        self.assertAlmostEqualMoney(self._inss(recibo) + self._inss(mensal), 368.60)

    def test_inss_mes_inteiro_em_ferias_nao_retem_no_mensal(self):
        """M02: o INSS todo foi retido no recibo; o mensal não retém nada."""
        emp, contract = self._contrato(4000.0)
        recibo = self._recibo(emp, contract, NOV_INI, NOV_FIM, 30)
        recibo.compute_sheet()
        mensal = self._create_payslip(emp, contract, NOV_INI, NOV_FIM)
        self.assertGreater(self._inss(recibo), 0)
        self.assertAlmostEqualMoney(self._inss(mensal), 0)

    def test_inss_sem_ferias_inalterado(self):
        emp, contract = self._contrato(3600.0)
        mensal = self._create_payslip(emp, contract, NOV_INI, NOV_FIM)
        self.assertAlmostEqualMoney(
            self._inss(mensal),
            mensal._get_tools_dict()["br"].calc_inss(3600.0),
        )

    def test_inss_recibo_cancelado_nao_entra(self):
        emp, contract = self._contrato(3600.0)
        recibo = self._recibo(emp, contract, date(2026, 11, 16), date(2026, 11, 25), 10)
        recibo.compute_sheet()
        recibo.action_payslip_cancel()
        mensal = self._create_payslip(emp, contract, NOV_INI, NOV_FIM)
        self.assertAlmostEqualMoney(
            self._inss(mensal), mensal._get_tools_dict()["br"].calc_inss(3600.0)
        )
