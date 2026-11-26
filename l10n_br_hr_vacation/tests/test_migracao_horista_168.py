# Copyright 2026 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""TG-168: a migração 18.0.1.20.0 troca as fórmulas só se forem as anteriores."""

import importlib.util

from odoo.tests import tagged
from odoo.tools import file_path

from .common import VacationCommon


@tagged("post_install", "-at_install")
class TestMigracaoHorista168(VacationCommon):
    def _modulo(self):
        caminho = file_path(
            "l10n_br_hr_vacation/migrations/18.0.1.20.0/post-migration.py"
        )
        spec = importlib.util.spec_from_file_location("mig_168", caminho)
        modulo = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(modulo)
        return modulo

    def test_troca_so_a_formula_anterior(self):
        modulo = self._modulo()
        novas = modulo._regras_novas()
        self.assertTrue(novas)
        regras = {
            xmlid: self.env.ref(f"l10n_br_hr_vacation.{xmlid}") for xmlid in novas
        }
        # Banco da 1.19.0: todas com a fórmula anterior, uma personalizada.
        personalizada = sorted(regras)[0]
        for xmlid, regra in regras.items():
            regra.amount_python_compute = modulo._antiga(novas[xmlid])
            self.assertNotIn("salario_referencia", regra.amount_python_compute)
        regras[personalizada].amount_python_compute += "\n# do cliente\n"
        personalizado = regras[personalizada].amount_python_compute
        with self.assertLogs("mig_168", "WARNING"):
            modulo.migrate(self.env.cr, "18.0.1.19.0")
        for xmlid, regra in regras.items():
            if xmlid == personalizada:
                self.assertEqual(regra.amount_python_compute, personalizado)
            else:
                self.assertEqual(
                    modulo._normaliza(regra.amount_python_compute),
                    modulo._normaliza(novas[xmlid]),
                )
        # Idempotente: rodar de novo não muda nada.
        antes = {x: r.amount_python_compute for x, r in regras.items()}
        modulo.migrate(self.env.cr, "18.0.1.19.0")
        self.assertEqual(antes, {x: r.amount_python_compute for x, r in regras.items()})
