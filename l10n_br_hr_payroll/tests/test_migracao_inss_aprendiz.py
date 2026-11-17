# Copyright 2026 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""TG-149: migração 18.0.1.13.0 do INSS do aprendiz (tabela, não 2%)."""

import importlib.util

from odoo.tests import tagged
from odoo.tools import file_path

from .common import PayrollCommon

CARREGADOR = "l10n_br_hr_payroll/migrations/18.0.1.13.0/post-migration.py"


@tagged("post_install", "-at_install")
class TestMigracaoInssAprendiz(PayrollCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        spec = importlib.util.spec_from_file_location(
            "mig_inss_149", file_path(CARREGADOR)
        )
        cls.mig = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.mig)
        cls.comum = cls.env.ref("l10n_br_hr_payroll.hr_rule_inss")
        cls.aprendiz = cls.env.ref("l10n_br_hr_payroll.hr_rule_inss_aprendiz")
        cls.comum_atual = cls.comum.amount_python_compute

    def _banco_1_11(self):
        """Regras como a 1.11.0 gravou (a do aprendiz ativa, na estrutura)."""
        self.comum.write(
            {
                "condition_select": "python",
                "condition_python": self.mig.CONDICAO_INSS_1_11,
                "amount_python_compute": self.mig.FORMULA_INSS_1_11,
            }
        )
        self.aprendiz.write(
            {
                "active": True,
                "condition_select": "python",
                "condition_python": self.mig.CONDICAO_APRENDIZ_1_11,
                "amount_python_compute": self.mig.FORMULA_APRENDIZ_1_11,
            }
        )
        self.structure_clt.write({"rule_ids": [(4, self.aprendiz.id)]})

    def _migrar(self):
        self.mig.migrate(self.env.cr, "18.0.1.12.0")

    def _inss(self, wage, tipo):
        emp = self._create_employee(name=f"E {tipo} {wage}", tipo_contrato=tipo)
        slip = self._create_payslip(emp, self._create_contract(emp, wage=wage))
        return self._get_line_total(slip, "INSS")

    def test_formula_da_1_11_e_a_do_xml_atual(self):
        """A fórmula "antiga" copiada aqui é a que o XML da 1.11.0 gravava."""
        self.assertEqual(
            self.mig._normaliza(self.mig.FORMULA_INSS_1_11),
            self.mig._normaliza(self.comum_atual),
        )

    def test_banco_da_1_11_passa_a_tabela_para_o_aprendiz(self):
        self._banco_1_11()
        self.assertAlmostEqualMoney(self._inss(1412.0, "aprendiz"), 28.24)  # 2%
        self._migrar()
        self.assertEqual(self.comum.condition_select, "none")
        self.assertFalse(self.aprendiz.active)
        self.assertAlmostEqualMoney(self._inss(1412.0, "aprendiz"), 105.90)
        self.assertAlmostEqualMoney(self._inss(1412.0, "clt"), 105.90)

    def test_idempotente(self):
        self._banco_1_11()
        self._migrar()
        antes = (self.comum.read()[0], self.aprendiz.read()[0])
        self._migrar()
        self.assertEqual((self.comum.read()[0], self.aprendiz.read()[0]), antes)

    def test_regra_do_aprendiz_personalizada_mantem_as_duas(self):
        self._banco_1_11()
        self.aprendiz.amount_python_compute = "result = 123.0"
        with self.assertLogs("mig_inss_149", "WARNING") as logs:
            self._migrar()
        self.assertIn("personalizada", logs.output[0])
        # a do aprendiz segue valendo; a comum segue sem ele (sem INSS em dobro)
        self.assertEqual(self.comum.condition_select, "python")
        self.assertTrue(self.aprendiz.active)
        self.assertAlmostEqualMoney(self._inss(1412.0, "aprendiz"), 123.0)

    def test_regra_comum_personalizada_mantem_as_duas(self):
        self._banco_1_11()
        self.comum.amount_python_compute = "result = 77.0"
        with self.assertLogs("mig_inss_149", "WARNING") as logs:
            self._migrar()
        self.assertIn("personalizada", logs.output[0])
        self.assertEqual(self.comum.condition_select, "python")
        self.assertEqual(self.comum.amount_python_compute, "result = 77.0")
        self.assertTrue(self.aprendiz.active)
        self.assertAlmostEqualMoney(self._inss(1412.0, "aprendiz"), 28.24)

    def test_estrutura_clt_perde_a_regra_inativa(self):
        """TG-149 (resíduo): a regra inativa sai da structure_clt migrada."""
        self._banco_1_11()
        self.assertIn(self.aprendiz, self.structure_clt.rule_ids)
        self._migrar()
        self.assertNotIn(self.aprendiz, self.structure_clt.rule_ids)
        self.assertIn(self.comum, self.structure_clt.rule_ids)

    def test_banco_ja_migrado_com_residuo_na_estrutura(self):
        """Banco que rodou a migração antes da limpeza: o -u seguinte limpa."""
        self._banco_1_11()
        self._migrar()
        self.structure_clt.write({"rule_ids": [(4, self.aprendiz.id)]})
        self._migrar()
        self.assertNotIn(self.aprendiz, self.structure_clt.rule_ids)

    def test_estrutura_personalizada_so_com_a_regra_do_aprendiz(self):
        """Sem a hr_rule_inss na estrutura o aprendiz ficaria sem INSS: inclui
        a regra comum e avisa."""
        self._banco_1_11()
        propria = self.env["hr.payroll.structure"].create(
            {
                "name": "Própria",
                "code": "PROPRIA149",
                "rule_ids": [(6, 0, [self.aprendiz.id])],
            }
        )
        with self.assertLogs("mig_inss_149", "WARNING") as logs:
            self._migrar()
        self.assertTrue(any("Própria" in linha for linha in logs.output))
        self.assertIn(self.comum, propria.rule_ids)
        self.assertNotIn(self.aprendiz, propria.rule_ids)
