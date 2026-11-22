# Copyright 2026 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""TG-159: migração 18.0.1.14.0 (DSR_HE passa a ler a categoria HE)."""

import importlib.util

from odoo.tests import tagged
from odoo.tests.common import TransactionCase
from odoo.tools import file_path, mute_logger

CONDICAO_1_13 = "result = (HE_50 + HE_100) > 0"
FORMULA_1_13 = "result = tools.br.dsr_reflexo(HE_50 + HE_100)"


@tagged("post_install", "-at_install")
class TestMigracaoDsrHe(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.dsr = cls.env.ref("l10n_br_hr_payroll.hr_rule_dsr_he")
        cls.he = cls.env.ref("l10n_br_hr_payroll.hr_salary_rule_category_he")
        cls.alw = cls.env.ref("l10n_br_hr_payroll.hr_salary_rule_category_alw")
        cls.he_50 = cls.env.ref("l10n_br_hr_payroll.hr_rule_he_50")
        cls.he_100 = cls.env.ref("l10n_br_hr_payroll.hr_rule_he_100")

    def _migrar(self):
        caminho = file_path(
            "l10n_br_hr_payroll/migrations/18.0.1.14.0/post-migration.py"
        )
        spec = importlib.util.spec_from_file_location("post_migration_tg159", caminho)
        modulo = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(modulo)
        with mute_logger("post_migration_tg159"):
            modulo.migrate(self.env.cr, "18.0.1.13.0")

    def _estado_1_13(self):
        self.dsr.write(
            {"condition_python": CONDICAO_1_13, "amount_python_compute": FORMULA_1_13}
        )
        self.he_50.category_id = self.alw
        self.he_100.category_id = self.alw

    def test_banco_padrao_move_as_regras_e_troca_a_formula(self):
        self._estado_1_13()
        self._migrar()
        self.assertEqual(self.he_50.category_id, self.he)
        self.assertEqual(self.he_100.category_id, self.he)
        self.assertIn("categories.HE", self.dsr.amount_python_compute)

    def test_categoria_personalizada_nao_troca_a_formula(self):
        """O DSR sumiria sem aviso se a fórmula nova não visse a HE_50."""
        self._estado_1_13()
        outra = self.env["hr.salary.rule.category"].create(
            {"name": "HE da casa", "code": "HE_CASA", "parent_id": self.alw.id}
        )
        self.he_50.category_id = outra
        self._migrar()
        self.assertEqual(self.he_50.category_id, outra)
        self.assertIn("HE_50 + HE_100", self.dsr.amount_python_compute)

    def test_idempotente(self):
        self._estado_1_13()
        self._migrar()
        formula = self.dsr.amount_python_compute
        self._migrar()
        self.assertEqual(self.dsr.amount_python_compute, formula)
