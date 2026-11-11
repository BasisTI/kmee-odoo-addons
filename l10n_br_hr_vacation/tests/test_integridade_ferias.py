# Copyright 2024 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""Integridade entre recibo de férias, mensal e rescisão (TG-83, 4ª ocorrência
da classe "holerites dependentes" da TG-82).

Só ações padrão do ORM e da tela (criar, calcular, confirmar, cancelar,
reabrir, excluir, escrever). Nenhum teste chama compute_sheet() no
dependente para "consertar" o estado: a reconciliação é da própria ação.
"""
import importlib.util
from datetime import date
from pathlib import Path
from unittest.mock import patch

from odoo.exceptions import UserError
from odoo.tests import tagged

from .test_ferias_folha_mensal import (
    DEZ_FIM,
    DEZ_INI,
    NOV_FIM,
    NOV_INI,
    TestFeriasFolhaMensal,
)

F_INI, F_FIM = date(2026, 11, 16), date(2026, 11, 25)


@tagged("post_install", "-at_install")
class TestIntegridadeFerias(TestFeriasFolhaMensal):
    def _mensal(self, emp, contract, de=NOV_INI, ate=NOV_FIM, calcular=True):
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

    def _rescisao(self, emp, contract, de=NOV_INI, ate=NOV_FIM):
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

    def _sal(self, slip):
        return self._get_line_total(slip, "SALARIO_BASE")

    def _saldo(self, slip):
        return self._get_line_total(slip, "SALDO_SALARIO")

    # -- recibo lançado, alterado, cancelado depois do mensal ---------------

    def test_a_recibo_tardio_recalcula_o_mensal_aberto(self):
        emp, contract = self._contrato()
        mensal = self._mensal(emp, contract)
        self.assertAlmostEqualMoney(self._sal(mensal), 3600)
        recibo = self._recibo(emp, contract, F_INI, F_FIM, 10)
        self.assertAlmostEqualMoney(self._sal(mensal), 2400)
        recibo.compute_sheet()  # agora o recibo tem GROSS e INSS
        self.assertAlmostEqualMoney(self._get_line_total(mensal, "INSS"), 248.60)

    def test_a_recibo_tardio_com_mensal_confirmado_e_recusado(self):
        emp, contract = self._contrato()
        mensal = self._mensal(emp, contract)
        mensal.action_payslip_done()
        with self.assertRaises(UserError):
            self._recibo(emp, contract, F_INI, F_FIM, 10)
        self.assertAlmostEqualMoney(self._sal(mensal), 3600)

    def test_b_cancelar_o_recibo_devolve_o_salario_ao_mensal(self):
        emp, contract = self._contrato()
        recibo = self._recibo(emp, contract, F_INI, F_FIM, 10)
        recibo.compute_sheet()
        mensal = self._mensal(emp, contract)
        self.assertAlmostEqualMoney(self._sal(mensal), 2400)
        recibo.action_payslip_cancel()
        self.assertAlmostEqualMoney(self._sal(mensal), 3600)
        self.assertAlmostEqualMoney(
            self._get_line_total(mensal, "INSS"),
            mensal._get_tools_dict()["br"].calc_inss(3600.0),
        )

    def test_b_cancelar_o_recibo_com_mensal_confirmado_e_recusado(self):
        emp, contract = self._contrato()
        recibo = self._recibo(emp, contract, F_INI, F_FIM, 10)
        recibo.compute_sheet()
        mensal = self._mensal(emp, contract)
        mensal.action_payslip_done()
        with self.assertRaises(UserError):
            recibo.action_payslip_cancel()
        self.assertNotEqual(recibo.state, "cancel")
        # voltando o mensal para rascunho, o cancelamento passa
        mensal.action_payslip_draft()
        recibo.action_payslip_cancel()
        self.assertEqual(recibo.state, "cancel")
        self.assertAlmostEqualMoney(self._sal(mensal), 3600)

    def test_c_calcular_o_recibo_atualiza_o_inss_do_mensal(self):
        emp, contract = self._contrato()
        recibo = self._recibo(emp, contract, F_INI, F_FIM, 10)
        mensal = self._mensal(emp, contract)
        sem_inss_do_recibo = self._get_line_total(mensal, "INSS")
        recibo.compute_sheet()
        self.assertAlmostEqualMoney(self._get_line_total(mensal, "INSS"), 248.60)
        self.assertNotAlmostEqual(
            self._get_line_total(mensal, "INSS"), sem_inss_do_recibo, places=2
        )

    def test_d_mudar_o_periodo_do_recibo_reconcilia_os_dois_meses(self):
        emp, contract = self._contrato(3000.0)
        recibo = self._recibo(emp, contract, F_INI, F_FIM, 10)
        nov = self._mensal(emp, contract)
        dez = self._mensal(emp, contract, DEZ_INI, DEZ_FIM)
        self.assertAlmostEqualMoney(self._sal(nov), 2000)
        self.assertAlmostEqualMoney(self._sal(dez), 3000)
        recibo.write({"date_from": date(2026, 12, 16), "date_to": date(2026, 12, 25)})
        self.assertAlmostEqualMoney(self._sal(nov), 3000)
        self.assertAlmostEqualMoney(self._sal(dez), 2000)

    def test_d_mudar_o_periodo_com_mensal_confirmado_e_recusado(self):
        emp, contract = self._contrato()
        recibo = self._recibo(emp, contract, F_INI, F_FIM, 10)
        mensal = self._mensal(emp, contract)
        mensal.action_payslip_done()
        with self.assertRaises(UserError):
            recibo.write(
                {"date_from": date(2026, 12, 16), "date_to": date(2026, 12, 25)}
            )
        self.assertEqual(recibo.date_from, F_INI)

    def test_mudar_os_dias_gozados_reconcilia(self):
        emp, contract = self._contrato()
        recibo = self._recibo(emp, contract, F_INI, F_FIM, 10)
        mensal = self._mensal(emp, contract)
        recibo.l10n_br_dias_periodo_gozado = 5
        self.assertAlmostEqualMoney(self._sal(mensal), 3000)

    def test_mudar_o_contrato_do_recibo_reconcilia(self):
        emp, contract = self._contrato()
        recibo = self._recibo(emp, contract, F_INI, F_FIM, 10)
        mensal = self._mensal(emp, contract)
        _outro_emp, outro = self._contrato(1000.0)
        recibo.contract_id = outro
        self.assertAlmostEqualMoney(self._sal(mensal), 3600)

    def test_mudar_a_estrutura_do_recibo_reconcilia(self):
        emp, contract = self._contrato()
        recibo = self._recibo(emp, contract, F_INI, F_FIM, 10)
        mensal = self._mensal(emp, contract)
        recibo.struct_id = self.structure_13
        self.assertAlmostEqualMoney(self._sal(mensal), 3600)

    def test_excluir_o_recibo_devolve_o_salario(self):
        emp, contract = self._contrato()
        recibo = self._recibo(emp, contract, F_INI, F_FIM, 10)
        mensal = self._mensal(emp, contract)
        recibo.unlink()
        self.assertAlmostEqualMoney(self._sal(mensal), 3600)

    def test_excluir_o_recibo_com_mensal_confirmado_e_recusado(self):
        emp, contract = self._contrato()
        recibo = self._recibo(emp, contract, F_INI, F_FIM, 10)
        mensal = self._mensal(emp, contract)
        mensal.action_payslip_done()
        with self.assertRaises(UserError):
            recibo.unlink()
        self.assertTrue(recibo.exists())

    def test_reabrir_o_recibo_cancelado_volta_a_descontar(self):
        emp, contract = self._contrato()
        recibo = self._recibo(emp, contract, F_INI, F_FIM, 10)
        recibo.action_payslip_cancel()
        mensal = self._mensal(emp, contract)
        self.assertAlmostEqualMoney(self._sal(mensal), 3600)
        recibo.action_payslip_draft()
        self.assertAlmostEqualMoney(self._sal(mensal), 2400)

    def test_reabrir_o_recibo_com_mensal_confirmado_e_recusado(self):
        emp, contract = self._contrato()
        recibo = self._recibo(emp, contract, F_INI, F_FIM, 10)
        recibo.action_payslip_cancel()
        mensal = self._mensal(emp, contract)
        mensal.action_payslip_done()
        with self.assertRaises(UserError):
            recibo.action_payslip_draft()
        self.assertEqual(recibo.state, "cancel")

    def test_confirmar_o_recibo_nao_mexe_no_mensal_confirmado(self):
        emp, contract = self._contrato()
        recibo = self._recibo(emp, contract, F_INI, F_FIM, 10)
        recibo.compute_sheet()
        mensal = self._mensal(emp, contract)
        mensal.action_payslip_done()
        recibo.action_payslip_done()
        self.assertEqual((recibo.state, mensal.state), ("done", "done"))

    def test_dois_recibos_e_dois_mensais_parciais(self):
        emp, contract = self._contrato(3000.0)
        r1 = self._recibo(emp, contract, date(2026, 11, 1), date(2026, 11, 10), 10)
        nov = self._mensal(emp, contract)
        dez = self._mensal(emp, contract, DEZ_INI, DEZ_FIM)
        r2 = self._recibo(emp, contract, date(2026, 12, 1), date(2026, 12, 5), 5)
        self.assertAlmostEqualMoney(self._sal(nov), 2000)
        self.assertAlmostEqualMoney(self._sal(dez), 2500)
        r1.action_payslip_cancel()
        self.assertAlmostEqualMoney(self._sal(nov), 3000)
        self.assertAlmostEqualMoney(self._sal(dez), 2500)
        r2.unlink()
        self.assertAlmostEqualMoney(self._sal(dez), 3000)

    # -- rescisão no mês das férias -------------------------------------------

    def test_e_rescisao_com_ferias_e_mensal_nao_paga_de_novo(self):
        """REPRO E: mensal 2.400 + férias 1.200 + saldo 0 (não 1.200)."""
        emp, contract = self._contrato()
        recibo = self._recibo(emp, contract, F_INI, F_FIM, 10)
        recibo.compute_sheet()
        mensal = self._mensal(emp, contract)
        rescisao = self._rescisao(emp, contract)
        self.assertAlmostEqualMoney(self._sal(mensal), 2400)
        self.assertAlmostEqualMoney(self._saldo(rescisao), 0)
        self.assertAlmostEqualMoney(self._get_line_total(recibo, "FERIAS"), 1200)

    def test_e_rescisao_com_ferias_sem_mensal_paga_so_os_dias_fora_das_ferias(self):
        emp, contract = self._contrato()
        recibo = self._recibo(emp, contract, F_INI, F_FIM, 10)
        recibo.compute_sheet()
        rescisao = self._rescisao(emp, contract)
        self.assertAlmostEqualMoney(self._saldo(rescisao), 2400)

    def test_recibo_tardio_recalcula_a_rescisao_aberta_sem_mensal(self):
        emp, contract = self._contrato()
        rescisao = self._rescisao(emp, contract)
        self.assertAlmostEqualMoney(self._saldo(rescisao), 3600)
        self._recibo(emp, contract, F_INI, F_FIM, 10)
        self.assertAlmostEqualMoney(self._saldo(rescisao), 2400)

    def test_recibo_tardio_com_rescisao_confirmada_e_recusado(self):
        emp, contract = self._contrato()
        rescisao = self._rescisao(emp, contract)
        rescisao.action_payslip_done()
        with self.assertRaises(UserError):
            self._recibo(emp, contract, F_INI, F_FIM, 10)

    def test_cancelar_o_recibo_devolve_os_dias_a_rescisao(self):
        emp, contract = self._contrato()
        recibo = self._recibo(emp, contract, F_INI, F_FIM, 10)
        rescisao = self._rescisao(emp, contract)
        self.assertAlmostEqualMoney(self._saldo(rescisao), 2400)
        recibo.action_payslip_cancel()
        self.assertAlmostEqualMoney(self._saldo(rescisao), 3600)

    def test_recibo_mensal_e_rescisao_em_cadeia(self):
        """Recibo tardio: mensal e rescisão abertos fecham o total sem duplicar."""
        emp, contract = self._contrato()
        mensal = self._mensal(emp, contract)
        rescisao = self._rescisao(emp, contract)
        recibo = self._recibo(emp, contract, F_INI, F_FIM, 10)
        recibo.compute_sheet()
        self.assertAlmostEqualMoney(self._sal(mensal), 2400)
        self.assertAlmostEqualMoney(self._saldo(rescisao), 0)
        self.assertAlmostEqualMoney(
            self._sal(mensal) + self._saldo(rescisao) + 1200, 3600
        )

    # -- rollback no meio da operação composta (Menor da TG-82 r5) ---------------

    def test_rollback_no_meio_do_compute_nao_deixa_participacao_velha(self):
        emp, contract = self._contrato()
        mensal = self._mensal(emp, contract)
        rescisao = self._rescisao(emp, contract)
        self.assertAlmostEqualMoney(self._saldo(rescisao), 0)
        mensal.action_payslip_cancel()
        self.assertAlmostEqualMoney(self._saldo(rescisao), 3600)
        with self.assertRaises(UserError), self.env.cr.savepoint():
            mensal.action_payslip_draft()
            with patch.object(
                type(mensal),
                "_get_baselocaldict",
                side_effect=UserError("falha injetada"),
            ):
                mensal.compute_sheet()
        self.assertEqual(mensal.state, "cancel")
        rescisao.invalidate_recordset()
        rescisao.action_payslip_done()
        with self.assertRaises(UserError):
            mensal.action_payslip_draft()
        self.assertEqual(mensal.state, "cancel")


@tagged("post_install", "-at_install")
class TestMigracaoSaldoSalarioFerias(TestFeriasFolhaMensal):
    """A migração 18.0.1.2.0 troca só a fórmula padrão antiga do SALDO_SALARIO."""

    def _migrar(self):
        caminho = Path(__file__).parent.parent / "migrations/18.0.1.2.0"
        spec = importlib.util.spec_from_file_location(
            "post_migration_vac_tg83", caminho / "post-migration.py"
        )
        modulo = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(modulo)
        modulo.migrate(self.env.cr, "18.0.1.1.0")
        return modulo

    def test_formula_padrao_antiga_e_atualizada(self):
        regra = self.env.ref("l10n_br_hr_vacation.hr_rule_saldo_salario")
        nova = regra.amount_python_compute
        regra.amount_python_compute = self._migrar().FORMULA_ANTIGA
        self._migrar()
        self.assertEqual(regra.amount_python_compute, nova)
        self.assertIn("dias_salario", nova)

    def test_formula_personalizada_e_preservada(self):
        regra = self.env.ref("l10n_br_hr_vacation.hr_rule_saldo_salario")
        regra.amount_python_compute = "result = 1.0"
        self._migrar()
        self.assertEqual(regra.amount_python_compute, "result = 1.0")
