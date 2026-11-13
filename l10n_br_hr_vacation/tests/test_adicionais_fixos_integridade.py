# Copyright 2026 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""TG-130: os três limites dos adicionais fixos em férias e rescisão.

1. o mensal entrega ao ponto único (``_l10n_br_participacao``) também a
   periculosidade e a insalubridade: a rescisão é recalculada quando só o
   adicional muda, e a confirmada recusa a mudança;
2. o saldo de salário contra o mensal já pago não deixa resíduo de R$ 0,01;
3. férias e 13º usam a média do adicional pago nos últimos 12 meses.
"""
import calendar
import importlib.util
from datetime import date

from odoo.exceptions import UserError
from odoo.tests import tagged
from odoo.tools import file_path

from .common import VacationCommon


@tagged("post_install", "-at_install")
class TestAdicionaisFixosIntegridade(VacationCommon):
    def _contrato(self, wage=3000.0, **flags):
        emp = self._create_employee()
        contract = self._create_contract(emp, wage=wage, date_start=date(2024, 1, 2))
        contract.write(flags)
        return emp, contract

    def _mensal(self, emp, contract, de, ate, calcular=True):
        slip = self.env["hr.payslip"].create(
            {
                "name": "Mensal %s" % de,
                "employee_id": emp.id,
                "contract_id": contract.id,
                "struct_id": self.structure_clt.id,
                "date_from": de,
                "date_to": ate,
                "company_id": self.env.company.id,
            }
        )
        if calcular:
            slip.compute_sheet()
        return slip

    def _rescisao(self, emp, contract, de, ate):
        contract.date_end = ate
        slip = self.env["hr.payslip"].create(
            {
                "name": "Rescisão",
                "employee_id": emp.id,
                "contract_id": contract.id,
                "struct_id": self.structure_rescisao.id,
                "date_from": de,
                "date_to": ate,
                "l10n_br_tipo_rescisao": "pedido_demissao",
                "l10n_br_aviso_previo": "nao_aplicavel",
                "company_id": self.env.company.id,
            }
        )
        slip.compute_sheet()
        return slip

    def _adicional(self, slip):
        return self._get_line_total(slip, "ADICIONAL_PERICULOSIDADE")

    def _saldo(self, slip):
        return self._get_line_total(slip, "SALDO_SALARIO")

    # --- 1. participação do mensal --------------------------------------

    def test_adicional_do_mensal_recalcula_a_rescisao_aberta(self):
        emp, contract = self._contrato()
        mensal = self._mensal(emp, contract, date(2025, 9, 1), date(2025, 9, 30))
        contract.l10n_br_periculosidade = True
        rescisao = self._rescisao(emp, contract, date(2025, 9, 1), date(2025, 9, 30))
        # O mensal ainda não pagou o adicional: a rescisão paga os R$ 900.
        self.assertAlmostEqualMoney(self._saldo(rescisao), 900.0)
        mensal.compute_sheet()
        self.assertAlmostEqualMoney(self._adicional(mensal), 900.0)
        # Só o adicional do mensal mudou: a rescisão não paga de novo.
        self.assertAlmostEqualMoney(self._saldo(rescisao), 0.0)

    def test_adicional_do_mensal_com_rescisao_confirmada_e_recusado(self):
        emp, contract = self._contrato()
        mensal = self._mensal(emp, contract, date(2025, 9, 1), date(2025, 9, 30))
        contract.l10n_br_periculosidade = True
        rescisao = self._rescisao(emp, contract, date(2025, 9, 1), date(2025, 9, 30))
        rescisao.action_payslip_done()
        with self.assertRaises(UserError):
            mensal.compute_sheet()
        self.assertAlmostEqualMoney(self._adicional(mensal), 0.0)
        self.assertAlmostEqualMoney(self._saldo(rescisao), 900.0)
        # Voltando a rescisão para rascunho, o recálculo passa.
        rescisao.action_payslip_draft()
        mensal.compute_sheet()
        self.assertAlmostEqualMoney(self._saldo(rescisao), 0.0)

    # --- 2. resíduo de R$ 0,01 ------------------------------------------

    def test_saldo_contra_mensal_pago_nao_deixa_residuo(self):
        # R$ 2.222,22 e 20 dias: o salário e o adicional arredondados um a um
        # somam R$ 0,01 a menos que a soma arredondada de uma vez.
        emp, contract = self._contrato(wage=2222.22, l10n_br_periculosidade=True)
        mensal = self._mensal(emp, contract, date(2025, 9, 1), date(2025, 9, 30))
        contract.date_end = date(2025, 9, 20)
        mensal.compute_sheet()
        rescisao = self._rescisao(emp, contract, date(2025, 9, 1), date(2025, 9, 20))
        self.assertAlmostEqualMoney(
            self._get_line_total(mensal, "SALARIO_BASE"), 1481.48
        )
        self.assertAlmostEqualMoney(self._adicional(mensal), 444.44)
        self.assertEqual(self._saldo(rescisao), 0.0)

    # --- 3. média duodecimal ---------------------------------------------

    def _historico(self, meses_com_adicional):
        """Mensais confirmados de 2025; o adicional some depois de N meses."""
        emp, contract = self._contrato(l10n_br_periculosidade=True)
        for mes in range(1, 13):
            if mes > meses_com_adicional:
                contract.l10n_br_periculosidade = False
            fim = date(2025, mes, calendar.monthrange(2025, mes)[1])
            self._mensal(emp, contract, date(2025, mes, 1), fim).action_payslip_done()
        return emp, contract

    def _recibo(self, emp, contract, dias):
        alloc = self.env["hr.leave.allocation"].create(
            {
                "employee_id": emp.id,
                "holiday_status_id": self.leave_type_ferias.id,
                "date_from": date(2024, 1, 2),
                "date_to": date(2025, 1, 1),
            }
        )
        alloc.action_validate()
        recibo = self.env["hr.payslip"].create(
            {
                "name": "Férias",
                "employee_id": emp.id,
                "contract_id": contract.id,
                "struct_id": self.structure_ferias.id,
                "date_from": date(2026, 1, 1),
                "date_to": date(2026, 1, 10),
                "company_id": self.env.company.id,
                "l10n_br_ferias_allocation_id": alloc.id,
                "l10n_br_dias_periodo_gozado": dias,
            }
        )
        recibo.compute_sheet()
        return recibo

    def test_ferias_de_quem_perdeu_o_adicional_usam_a_media(self):
        emp, contract = self._historico(10)
        self.assertFalse(contract.l10n_br_periculosidade)
        recibo = self._recibo(emp, contract, 10)
        # Média: R$ 900 em 10 dos 12 mensais = R$ 750.
        self.assertAlmostEqualMoney(
            self._get_line_total(recibo, "FERIAS"), round((3000 + 750) * 10 / 30, 2)
        )

    def test_ferias_de_quem_tem_o_adicional_hoje_usam_o_valor_cheio(self):
        emp, contract = self._historico(10)
        contract.l10n_br_periculosidade = True
        recibo = self._recibo(emp, contract, 10)
        self.assertAlmostEqualMoney(
            self._get_line_total(recibo, "FERIAS"), round((3000 + 900) * 10 / 30, 2)
        )

    def test_decimo_terceiro_de_quem_perdeu_o_adicional_usa_a_media(self):
        emp, contract = self._historico(10)
        decimo = self.env["hr.payslip"].create(
            {
                "name": "13º",
                "employee_id": emp.id,
                "contract_id": contract.id,
                "struct_id": self.structure_13.id,
                "date_from": date(2026, 1, 1),
                "date_to": date(2026, 1, 31),
                "company_id": self.env.company.id,
            }
        )
        decimo.compute_sheet()
        avos = decimo.l10n_br_avos_13
        self.assertGreater(avos, 0)
        self.assertAlmostEqualMoney(
            self._get_line_total(decimo, "DECIMO_TERCEIRO_BRUTO"),
            round((3000 + 750) * avos / 12, 2),
        )

    def test_sem_historico_vale_o_adicional_vigente(self):
        emp, contract = self._contrato(l10n_br_periculosidade=True)
        recibo = self._recibo(emp, contract, 10)
        self.assertAlmostEqualMoney(
            self._get_line_total(recibo, "FERIAS"), round((3000 + 900) * 10 / 30, 2)
        )

    def test_migracao_do_saldo_troca_so_a_formula_da_1_3_0(self):
        saldo = self.env.ref("l10n_br_hr_vacation.hr_rule_saldo_salario")
        arquivo = file_path(
            "l10n_br_hr_vacation/migrations/18.0.1.4.0/post-migration.py"
        )
        spec = importlib.util.spec_from_file_location("migracao_tg130", arquivo)
        modulo = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(modulo)
        nova = saldo.amount_python_compute
        saldo.amount_python_compute = modulo.FORMULA_ANTIGA
        modulo.migrate(self.env.cr, "18.0.1.3.1")
        self.env.invalidate_all()
        self.assertEqual(saldo.amount_python_compute.strip(), nova.strip())
        saldo.amount_python_compute = "result = 123.0"
        modulo.migrate(self.env.cr, "18.0.1.3.1")
        self.env.invalidate_all()
        self.assertEqual(saldo.amount_python_compute, "result = 123.0")
