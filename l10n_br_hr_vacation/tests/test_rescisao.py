# Copyright 2024 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""
Testes ORM: Rescisão (verbas rescisórias seguras).

Cobertura:
  - Saldo de salário proporcional aos dias trabalhados
  - 13º proporcional (incidência de INSS/IRRF/FGTS separada)
  - Férias proporcionais + 1/3 (indenizatórias: isentas de INSS/IRRF/FGTS)
  - Composição do NET
"""
from datetime import date

from odoo.exceptions import UserError
from odoo.tests import tagged

from .common import VacationCommon


@tagged("post_install", "-at_install")
class TestRescisao(VacationCommon):
    """Testes das verbas rescisórias implementadas."""

    def _rescisao(self, wage=3000.00, date_start=None, date_from=None, date_to=None):
        emp = self._create_employee("Rescisão")
        contract = self._create_contract(
            emp, wage=wage, date_start=date_start or date(2024, 1, 1)
        )
        rescisao = self.env["hr.payslip"].create(
            {
                "name": "Rescisão",
                "employee_id": emp.id,
                "contract_id": contract.id,
                "date_from": date_from or date(2024, 9, 1),
                "date_to": date_to or date(2024, 9, 30),
                "struct_id": self.structure_rescisao.id,
                "company_id": self.env.company.id,
            }
        )
        rescisao.compute_sheet()
        return rescisao

    def test_saldo_salario_mes_cheio(self):
        """Rescisão no dia 30: saldo de salário = salário integral."""
        rescisao = self._rescisao(wage=3000.00)
        self.assertAlmostEqualMoney(
            self._get_line_total(rescisao, "SALDO_SALARIO"), 3000.00
        )

    def test_saldo_salario_proporcional_dias(self):
        """Rescisão no dia 15: saldo = 15/30 do salário."""
        rescisao = self._rescisao(
            wage=3000.00, date_from=date(2024, 9, 1), date_to=date(2024, 9, 15)
        )
        self.assertAlmostEqualMoney(
            self._get_line_total(rescisao, "SALDO_SALARIO"), 1500.00
        )

    def test_saldo_salario_contrato_iniciado_no_meio_do_mes(self):
        """RF-06: contrato iniciado dia 10/09, rescisão dia 30/09→ 21 dias.

        Antes, o cálculo assumia sempre início no dia 1º (``date_to.day``),
        pagando 30 dias mesmo quando o contrato começou no meio do mês.
        """
        rescisao = self._rescisao(
            wage=3000.00, date_start=date(2024, 9, 10), date_to=date(2024, 9, 30)
        )
        # 10 a 30/09 = 21 dias.
        self.assertAlmostEqualMoney(
            self._get_line_total(rescisao, "SALDO_SALARIO"), 3000.00 * 21 / 30
        )

    def test_decimo_proporcional_avos(self):
        """13º proporcional aos avos até a rescisão (9/12)."""
        rescisao = self._rescisao(wage=3000.00)
        self.assertAlmostEqualMoney(
            self._get_line_total(rescisao, "DECIMO_RESCISAO"), 2250.00
        )

    def test_ferias_proporcionais_com_terco(self):
        """Férias proporcionais (9/12) + 1/3 constitucional."""
        rescisao = self._rescisao(wage=3000.00)
        ferias = self._get_line_total(rescisao, "FERIAS_INDENIZADAS")
        adicional = self._get_line_total(rescisao, "ADICIONAL_FERIAS_INDENIZADAS")
        self.assertEqual(rescisao.l10n_br_avos_ferias, 9)
        self.assertAlmostEqualMoney(ferias, 2250.00)  # 9/12 x 3000
        self.assertAlmostEqualMoney(adicional, 750.00)  # 1/3 de 2250

    def test_ferias_indenizadas_isentas(self):
        """Férias indenizadas + 1/3 não sofrem INSS, IRRF nem FGTS.

        Prova indireta: o INSS incide só sobre o saldo de salário e o
        INSS_13 só sobre o 13º; o FGTS idem. Se as férias indenizadas
        entrassem em alguma base, os valores mudariam.
        """
        rescisao = self._rescisao(wage=3000.00)
        saldo = self._get_line_total(rescisao, "SALDO_SALARIO")
        inss = self._get_line_total(rescisao, "INSS")
        inss_13 = self._get_line_total(rescisao, "INSS_13")
        decimo = self._get_line_total(rescisao, "DECIMO_RESCISAO")
        # INSS do saldo bate com INSS sobre o próprio saldo (não sobre saldo+férias)
        base_inss = self._get_line_total(rescisao, "BASE_IRRF") + inss
        # BASE_IRRF = saldo - inss - deps - pensao; sem dependentes/pensão => saldo-inss
        self.assertAlmostEqualMoney(base_inss, saldo)
        self.assertGreater(inss, 0.0)
        self.assertGreater(inss_13, 0.0)
        # FGTS só sobre saldo e 13º:
        fgts = self._get_line_total(rescisao, "FGTS")
        fgts_13 = self._get_line_total(rescisao, "FGTS_13")
        self.assertAlmostEqualMoney(fgts, round(saldo * 0.08, 2))
        self.assertAlmostEqualMoney(fgts_13, round(decimo * 0.08, 2))

    def test_net_composicao(self):
        """NET = saldo + 13º + férias + 1/3 - INSS - INSS_13 - IRRF - IRRF_13."""
        rescisao = self._rescisao(wage=3000.00)
        g = lambda c: self._get_line_total(rescisao, c)  # noqa: E731
        esperado = (
            g("SALDO_SALARIO")
            + g("DECIMO_RESCISAO")
            + g("FERIAS_INDENIZADAS")
            + g("ADICIONAL_FERIAS_INDENIZADAS")
            - g("INSS")
            - g("INSS_13")
            - g("IRRF")
            - g("IRRF_13")
        )
        self.assertAlmostEqualMoney(g("NET"), esperado)
        self.assertGreater(g("NET"), 0.0)

    def test_avos_ferias_periodo_aquisitivo_em_curso(self):
        """Avos de férias contam apenas o período aquisitivo em curso."""
        Payslip = self.env["hr.payslip"]
        # Admitido há mais de 1 ano: período em curso reinicia no aniversário.
        avos = Payslip._calc_avos_ferias_proporcionais(
            date(2022, 3, 15), date(2024, 9, 30)
        )
        # Período em curso: 15/03/2024 -> 30/09/2024 = ~6,5 meses => 7 avos
        self.assertEqual(avos, 7)


@tagged("post_install", "-at_install")
class TestSaldoSalarioCompensado(VacationCommon):
    """Mensal + rescisão do mesmo período pagam os dias uma única vez (TG-82)."""

    def _holerites(self, mensal=True):
        emp = self._create_employee("Saldo compensado")
        contract = self._create_contract(emp, wage=5000.00, date_start=date(2023, 1, 2))
        contract.date_end = date(2026, 10, 20)
        mensal_slip = None
        if mensal:
            mensal_slip = self.env["hr.payslip"].create(
                {
                    "name": "Mensal",
                    "employee_id": emp.id,
                    "contract_id": contract.id,
                    "struct_id": self.structure_clt.id,
                    "date_from": date(2026, 10, 1),
                    "date_to": date(2026, 10, 31),
                    "company_id": self.env.company.id,
                }
            )
            mensal_slip.compute_sheet()
        rescisao = self.env["hr.payslip"].create(
            {
                "name": "Rescisão",
                "employee_id": emp.id,
                "contract_id": contract.id,
                "struct_id": self.structure_rescisao.id,
                "date_from": date(2026, 10, 1),
                "date_to": date(2026, 10, 20),
                "company_id": self.env.company.id,
            }
        )
        rescisao.compute_sheet()
        return mensal_slip, rescisao

    def test_mensal_mais_rescisao_pagam_os_20_dias_uma_vez(self):
        mensal, rescisao = self._holerites()
        total_mensal = self._get_line_total(mensal, "SALARIO_BASE")
        saldo = self._get_line_total(rescisao, "SALDO_SALARIO")
        self.assertAlmostEqualMoney(total_mensal, 3333.33)
        self.assertAlmostEqualMoney(total_mensal + saldo, 3333.33)

    def test_sem_mensal_a_rescisao_paga_o_saldo_inteiro(self):
        _mensal, rescisao = self._holerites(mensal=False)
        self.assertAlmostEqualMoney(
            self._get_line_total(rescisao, "SALDO_SALARIO"), 3333.33
        )

    def test_mensal_cancelado_nao_compensa(self):
        mensal, rescisao = self._holerites()
        mensal.write({"state": "cancel"})
        rescisao.compute_sheet()
        self.assertAlmostEqualMoney(
            self._get_line_total(rescisao, "SALDO_SALARIO"), 3333.33
        )


@tagged("post_install", "-at_install")
class TestCicloCompensacaoMensalRescisao(VacationCommon):
    """Os dias do saldo nunca são pagos em dobro nem somem (TG-82, classe
    "integridade da compensação mensal x rescisão"), qualquer que seja a
    ordem das ações padrão. Nenhum teste chama compute_sheet() só para
    "consertar" o estado: a reconciliação é da própria ação."""

    def _contrato(self):
        emp = self._create_employee("Ciclo compensação")
        contract = self._create_contract(emp, wage=5000.00, date_start=date(2023, 1, 2))
        contract.date_end = date(2026, 10, 20)
        return emp, contract

    def _holerite(self, emp, contract, struct, de, ate, nome):
        return self.env["hr.payslip"].create(
            {
                "name": nome,
                "employee_id": emp.id,
                "contract_id": contract.id,
                "struct_id": struct.id,
                "date_from": de,
                "date_to": ate,
                "company_id": self.env.company.id,
            }
        )

    def _mensal(self, emp, contract, de=None, ate=None):
        de = de or date(2026, 10, 1)
        ate = ate or date(2026, 10, 31)
        return self._holerite(emp, contract, self.structure_clt, de, ate, "Mensal")

    def _rescisao(self, emp, contract):
        return self._holerite(
            emp,
            contract,
            self.structure_rescisao,
            date(2026, 10, 1),
            date(2026, 10, 20),
            "Rescisão",
        )

    def _pago(self, *slips):
        return sum(self._get_line_total(s, "SALARIO_BASE") for s in slips)

    def _total(self, mensais, rescisao):
        return self._pago(*mensais) + self._get_line_total(rescisao, "SALDO_SALARIO")

    def test_a_rescisao_calculada_antes_do_mensal(self):
        emp, contract = self._contrato()
        rescisao = self._rescisao(emp, contract)
        rescisao.compute_sheet()
        self.assertAlmostEqualMoney(
            self._get_line_total(rescisao, "SALDO_SALARIO"), 3333.33
        )
        mensal = self._mensal(emp, contract)
        mensal.compute_sheet()
        self.assertAlmostEqualMoney(self._total([mensal], rescisao), 3333.33)
        self.assertAlmostEqualMoney(
            self._get_line_total(rescisao, "SALDO_SALARIO"), 0.0
        )

    def test_a_rescisao_confirmada_recusa_calcular_o_mensal(self):
        emp, contract = self._contrato()
        rescisao = self._rescisao(emp, contract)
        rescisao.compute_sheet()
        rescisao.action_payslip_done()
        mensal = self._mensal(emp, contract)
        with self.assertRaises(UserError):
            mensal.compute_sheet()

    def test_b_cancelar_o_mensal_devolve_o_saldo_a_rescisao(self):
        emp, contract = self._contrato()
        mensal = self._mensal(emp, contract)
        mensal.compute_sheet()
        rescisao = self._rescisao(emp, contract)
        rescisao.compute_sheet()
        self.assertAlmostEqualMoney(
            self._get_line_total(rescisao, "SALDO_SALARIO"), 0.0
        )
        mensal.action_payslip_cancel()
        self.assertEqual(mensal.state, "cancel")
        self.assertAlmostEqualMoney(
            self._get_line_total(rescisao, "SALDO_SALARIO"), 3333.33
        )

    def test_b_rescisao_confirmada_recusa_cancelar_o_mensal(self):
        emp, contract = self._contrato()
        mensal = self._mensal(emp, contract)
        mensal.compute_sheet()
        rescisao = self._rescisao(emp, contract)
        rescisao.compute_sheet()
        rescisao.action_payslip_done()
        with self.assertRaises(UserError):
            mensal.action_payslip_cancel()
        self.assertNotEqual(mensal.state, "cancel")
        # voltando a rescisão para rascunho, o cancelamento do mensal passa
        rescisao.action_payslip_draft()
        mensal.action_payslip_cancel()
        self.assertEqual(mensal.state, "cancel")

    def test_mensal_recalculado_depois_da_rescisao(self):
        emp, contract = self._contrato()
        mensal = self._mensal(emp, contract)
        mensal.compute_sheet()
        rescisao = self._rescisao(emp, contract)
        rescisao.compute_sheet()
        contract.wage = 6000.00
        mensal.compute_sheet()
        self.assertAlmostEqualMoney(self._pago(mensal), 4000.00)
        self.assertAlmostEqualMoney(self._total([mensal], rescisao), 4000.00)

    def test_rescisao_confirmada_mensal_confirmado_sem_mudanca(self):
        emp, contract = self._contrato()
        mensal = self._mensal(emp, contract)
        mensal.compute_sheet()
        rescisao = self._rescisao(emp, contract)
        rescisao.compute_sheet()
        rescisao.action_payslip_done()
        # confirmar o mensal recalcula, mas nada muda: não deve recusar
        mensal.action_payslip_done()
        self.assertEqual(mensal.state, "done")
        self.assertAlmostEqualMoney(self._total([mensal], rescisao), 3333.33)

    def test_mensal_voltado_para_rascunho_continua_compensando(self):
        emp, contract = self._contrato()
        mensal = self._mensal(emp, contract)
        mensal.compute_sheet()
        mensal.action_payslip_done()
        rescisao = self._rescisao(emp, contract)
        rescisao.compute_sheet()
        mensal.action_payslip_draft()
        rescisao.compute_sheet()
        self.assertAlmostEqualMoney(self._total([mensal], rescisao), 3333.33)
        # e cancelá-lo depois devolve o saldo sem recálculo manual
        mensal.action_payslip_cancel()
        self.assertAlmostEqualMoney(
            self._get_line_total(rescisao, "SALDO_SALARIO"), 3333.33
        )

    def test_excluir_o_mensal_em_rascunho_devolve_o_saldo(self):
        emp, contract = self._contrato()
        mensal = self._mensal(emp, contract)
        mensal.compute_sheet()
        rescisao = self._rescisao(emp, contract)
        rescisao.compute_sheet()
        mensal.action_payslip_draft()
        mensal.unlink()
        self.assertAlmostEqualMoney(
            self._get_line_total(rescisao, "SALDO_SALARIO"), 3333.33
        )

    def test_dois_mensais_parciais(self):
        emp, contract = self._contrato()
        m1 = self._mensal(emp, contract, date(2026, 10, 1), date(2026, 10, 10))
        m2 = self._mensal(emp, contract, date(2026, 10, 11), date(2026, 10, 31))
        rescisao = self._rescisao(emp, contract)
        rescisao.compute_sheet()
        m1.compute_sheet()
        m2.compute_sheet()
        self.assertAlmostEqualMoney(self._total([m1, m2], rescisao), 3333.33, places=1)
        m2.action_payslip_cancel()
        self.assertAlmostEqualMoney(self._total([m1], rescisao), 3333.33, places=1)
