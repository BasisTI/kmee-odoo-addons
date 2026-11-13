# Copyright 2026 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""TG-128: migração do adicional noturno cobre as fórmulas padrão antigas."""

import importlib.util

from odoo.tests import tagged
from odoo.tests.common import TransactionCase
from odoo.tools import file_path, mute_logger

ANTIGAS = {
    "jornada_computadas_0_20": (
        "salario_hora = contract.wage / contract._l10n_br_divisor_horas_mensais()\n"
        "result = tools.br.round_money("
        "salario_hora * 0.20 * payslip.l10n_br_horas_noturnas_computadas)"
    ),
    "220_sem_arredondar": (
        "salario_hora = contract.wage / 220\n"
        "result = salario_hora * 0.20 * payslip.l10n_br_horas_noturnas"
    ),
    "220_arredondada": (
        "salario_hora = contract.wage / 220\n"
        "result = tools.br.round_money("
        "salario_hora * 0.20 * payslip.l10n_br_horas_noturnas)"
    ),
    "jornada_arredondada": (
        "salario_hora = contract.wage / contract._l10n_br_divisor_horas_mensais()\n"
        "result = tools.br.round_money("
        "salario_hora * 0.20 * payslip.l10n_br_horas_noturnas)"
    ),
}


@tagged("post_install", "-at_install")
class TestMigracaoHoraReduzida(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.regra = cls.env.ref("l10n_br_hr_payroll.hr_rule_adicional_noturno")
        cls.atual = cls.regra.amount_python_compute

    def _migrar(self):
        caminho = file_path(
            "l10n_br_hr_payroll/migrations/18.0.1.10.0/post-migration.py"
        )
        spec = importlib.util.spec_from_file_location("post_migration_tg128", caminho)
        modulo = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(modulo)
        with mute_logger("post_migration_tg128"):
            modulo.migrate(self.env.cr, "18.0.1.9.0")

    def test_cada_formula_padrao_antiga_e_atualizada(self):
        for nome, formula in ANTIGAS.items():
            with self.subTest(nome):
                self.regra.amount_python_compute = (
                    "\n" + formula.replace("\n", "\n    ") + "\n        "
                )
                self._migrar()
                self.assertIn(
                    "l10n_br_horas_noturnas_computadas",
                    self.regra.amount_python_compute,
                )

    def test_divisor_220_e_mantido(self):
        """M6: a migração não troca o divisor do banco antigo sem querer."""
        self.regra.amount_python_compute = ANTIGAS["220_arredondada"]
        self._migrar()
        formula = self.regra.amount_python_compute
        self.assertIn("contract.wage / 220", formula)
        self.assertNotIn("_l10n_br_divisor_horas_mensais", formula)
        self.assertIn("l10n_br_horas_noturnas_computadas", formula)
        self.assertIn("l10n_br_adicional_noturno_perc", formula)

    def test_divisor_da_jornada_e_mantido(self):
        self.regra.amount_python_compute = ANTIGAS["jornada_arredondada"]
        self._migrar()
        self.assertIn(
            "_l10n_br_divisor_horas_mensais", self.regra.amount_python_compute
        )

    def test_rascunho_alinha_ao_contrato_e_confirmado_fica(self):
        """M5: rascunho anterior ao upgrade passa a seguir o contrato."""
        emp = self.env["hr.employee"].create({"name": "Maria Rural Teste"})
        contrato = self.env["hr.contract"].create(
            {
                "name": "Contrato Maria",
                "employee_id": emp.id,
                "wage": 3000.0,
                "date_start": "2024-01-01",
                "state": "open",
                "struct_id": self.env.ref("l10n_br_hr_payroll.structure_clt").id,
            }
        )

        def holerite(inicio, fim):
            return self.env["hr.payslip"].create(
                {
                    "name": "H",
                    "employee_id": emp.id,
                    "contract_id": contrato.id,
                    "struct_id": contrato.struct_id.id,
                    "date_from": inicio,
                    "date_to": fim,
                    "l10n_br_usar_hora_reduzida": False,
                }
            )

        rascunho = holerite("2024-03-01", "2024-03-31")
        fechado = holerite("2024-04-01", "2024-04-30")
        fechado.state = "done"
        self._migrar()
        rascunho.invalidate_recordset()
        fechado.invalidate_recordset()
        self.assertTrue(rascunho.l10n_br_usar_hora_reduzida)
        self.assertFalse(fechado.l10n_br_usar_hora_reduzida)

    def test_formula_personalizada_e_preservada(self):
        custom = "result = contract.wage * 0.35 * payslip.l10n_br_horas_noturnas"
        self.regra.amount_python_compute = custom
        self._migrar()
        self.assertEqual(self.regra.amount_python_compute, custom)

    def test_idempotente(self):
        self.regra.amount_python_compute = ANTIGAS["jornada_arredondada"]
        self._migrar()
        primeira = self.regra.amount_python_compute
        self._migrar()
        self.assertEqual(self.regra.amount_python_compute, primeira)
        self.assertEqual(primeira.strip(), self.atual.strip())
