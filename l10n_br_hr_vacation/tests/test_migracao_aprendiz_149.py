# Copyright 2026 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""TG-149: migração 18.0.1.16.0 troca só a regra igual à da 1.14.0."""
import importlib.util

from odoo.tests import tagged
from odoo.tools import file_path

from .common import VacationCommon

CONDICAO_1_14 = "result = employee.l10n_br_tipo_contrato != 'aprendiz'"
FORMULAS_1_14 = {
    "hr_rule_fgts_ferias": "result = tools.br.round_money(max(categories.GROSS, 0) * 0.08)",
    "hr_rule_fgts_rescisao": "result = tools.br.round_money(max(SALDO_SALARIO, 0) * 0.08)",
}
XMLIDS = (
    "hr_rule_fgts_ferias",
    "hr_rule_fgts_rescisao",
    "hr_rule_inss_rescisao",
    "hr_rule_inss_13_rescisao",
)


@tagged("post_install", "-at_install")
class TestMigracaoAprendiz149(VacationCommon):
    def _regra(self, xmlid):
        return self.env.ref(f"l10n_br_hr_vacation.{xmlid}")

    def _para_1_14(self):
        """Devolve as regras ao estado gravado pela 1.14.0."""
        for xmlid in XMLIDS:
            valores = {
                "condition_select": "python",
                "condition_python": CONDICAO_1_14,
            }
            if xmlid in FORMULAS_1_14:
                valores["amount_python_compute"] = FORMULAS_1_14[xmlid]
            self._regra(xmlid).write(valores)

    def _migrar(self):
        caminho = file_path(
            "l10n_br_hr_vacation/migrations/18.0.1.16.0/post-migration.py"
        )
        spec = importlib.util.spec_from_file_location("mig_149", caminho)
        modulo = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(modulo)
        modulo.migrate(self.env.cr, "18.0.1.15.0")

    def test_banco_da_1_14_e_atualizado(self):
        novos = {x: self._regra(x).amount_python_compute for x in XMLIDS}
        self._para_1_14()
        self._migrar()
        for xmlid in XMLIDS:
            regra = self._regra(xmlid)
            self.assertEqual(regra.condition_select, "none", xmlid)
            self.assertEqual(regra.amount_python_compute, novos[xmlid], xmlid)
        self.assertIn("0.02", self._regra("hr_rule_fgts_ferias").amount_python_compute)
        self.assertIn(
            "0.02", self._regra("hr_rule_fgts_rescisao").amount_python_compute
        )

    def test_banco_migrado_fica_igual(self):
        antes = {x: self._regra(x).read()[0] for x in XMLIDS}
        self._migrar()
        for xmlid in XMLIDS:
            self.assertEqual(self._regra(xmlid).read()[0], antes[xmlid], xmlid)

    def test_formula_de_fgts_personalizada_e_mantida_com_a_condicao(self):
        self._para_1_14()
        fgts = self._regra("hr_rule_fgts_ferias")
        fgts.amount_python_compute = "result = 1.0"
        with self.assertLogs("mig_149", "WARNING") as logs:
            self._migrar()
        self.assertEqual(len(logs.output), 1)
        self.assertIn("personalizada", logs.output[0])
        self.assertEqual(fgts.amount_python_compute, "result = 1.0")
        # Sem a condição o aprendiz passaria a receber o valor da fórmula dela.
        self.assertEqual(fgts.condition_select, "python")
        for xmlid in ("hr_rule_fgts_rescisao", "hr_rule_inss_rescisao"):
            self.assertEqual(self._regra(xmlid).condition_select, "none")

    def test_condicao_do_inss_personalizada_e_mantida(self):
        self._para_1_14()
        inss = self._regra("hr_rule_inss_rescisao")
        inss.condition_python = "result = employee.l10n_br_tipo_contrato == 'clt'"
        with self.assertLogs("mig_149", "WARNING") as logs:
            self._migrar()
        self.assertIn("personalizada", logs.output[0])
        self.assertEqual(inss.condition_select, "python")
        self.assertEqual(
            inss.condition_python, "result = employee.l10n_br_tipo_contrato == 'clt'"
        )
