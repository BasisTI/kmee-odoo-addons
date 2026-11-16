# Copyright 2026 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""TG-138: migração 18.0.1.14.0 troca só a fórmula igual à da versão anterior."""
import importlib.util

from odoo.tests import tagged
from odoo.tools import file_path

from .common import VacationCommon


@tagged("post_install", "-at_install")
class TestMigracaoFgts138(VacationCommon):
    def _migrar(self):
        caminho = file_path(
            "l10n_br_hr_vacation/migrations/18.0.1.14.0/post-migration.py"
        )
        spec = importlib.util.spec_from_file_location("mig_138", caminho)
        modulo = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(modulo)
        modulo.migrate(self.env.cr, "18.0.1.13.0")

    def test_banco_antigo_e_atualizado(self):
        multa = self.env.ref("l10n_br_hr_vacation.hr_rule_multa_fgts")
        fgts13 = self.env.ref("l10n_br_hr_vacation.hr_rule_fgts_13")
        novo_multa = multa.amount_python_compute
        multa.amount_python_compute = novo_multa.replace(
            "_l10n_br_fgts_13_na_base_multa", "_l10n_br_fgts_13_primeira_depositado"
        )
        fgts13.write(
            {
                "condition_select": "python",
                "condition_python": "result = employee.l10n_br_tipo_contrato != 'aprendiz'",
                "amount_python_compute": fgts13.amount_python_compute.replace(
                    "(0.02 if employee.l10n_br_tipo_contrato == 'aprendiz' else 0.08)",
                    "0.08",
                ),
            }
        )
        self.structure_13.rule_ids = [
            (3, self.env.ref("l10n_br_hr_vacation.hr_rule_desconto_adiantamento_13").id)
        ]
        self._migrar()
        self.assertEqual(multa.amount_python_compute, novo_multa)
        self.assertEqual(fgts13.condition_select, "none")
        self.assertIn("0.02", fgts13.amount_python_compute)
        self.assertIn("ADIANTAMENTO_13", self.structure_13.rule_ids.mapped("code"))

    def test_regra_personalizada_e_mantida(self):
        multa = self.env.ref("l10n_br_hr_vacation.hr_rule_multa_fgts")
        multa.amount_python_compute = "result = 1.0"
        self._migrar()
        self.assertEqual(multa.amount_python_compute, "result = 1.0")
