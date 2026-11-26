# Copyright 2026 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""TG-168: Menores da TG-166 (valor da hora que sobra, wage descartado, migração)."""

import importlib.util

from odoo.tests import tagged
from odoo.tools import file_path

from .common import PayrollCommon


@tagged("post_install", "-at_install")
class TestHoristaMenores168(PayrollCommon):
    def _contrato(self, wage=3600.0):
        emp = self._create_employee("Menor 168")
        return self._create_contract(emp, wage=wage)

    def test_valor_hora_velho_nao_volta_ao_retornar_a_hourly(self):
        contract = self._contrato()
        contract.write(
            {"salary_unit": self._unidade_salario("1").id, "l10n_br_valor_hora": 20.0}
        )
        contract.write({"salary_unit": self._unidade_salario("5").id, "wage": 3600.0})
        self.assertEqual(contract.l10n_br_valor_hora, 0.0)
        self.assertEqual(contract.wage, 3600.0)
        # Volta a Hourly com o valor novo: o mensal vem dele, não do antigo.
        contract.write(
            {"salary_unit": self._unidade_salario("1").id, "l10n_br_valor_hora": 25.0}
        )
        self.assertEqual(
            contract.wage, round(25.0 * contract._l10n_br_divisor_horas_mensais(), 2)
        )

    def test_wage_em_hourly_sem_valor_hora_nao_e_descartado(self):
        contract = self._contrato()
        # Hourly de banco antigo: a unidade entra sem valor da hora (SQL, como a
        # migração 1.15.0 deixou).
        unidade = self._unidade_salario("1")
        self.env.cr.execute(
            "UPDATE hr_contract SET salary_unit = %s, l10n_br_valor_hora = 0 "
            "WHERE id = %s",
            (unidade.id, contract.id),
        )
        contract.invalidate_recordset()
        contract.write({"wage": 4200.0})
        self.assertEqual(contract.wage, 4200.0)

    def test_wage_com_valor_hora_continua_calculado(self):
        contract = self._contrato()
        contract.write(
            {"salary_unit": self._unidade_salario("1").id, "l10n_br_valor_hora": 20.0}
        )
        calculado = contract.wage
        contract.write({"wage": 1.0})
        self.assertEqual(contract.wage, calculado)

    def test_migracao_avisa_unidades_nao_suportadas(self):
        contract = self._contrato()
        contract.write({"salary_unit": self._unidade_salario("3").id})
        self.env.flush_all()
        for versao in ("18.0.1.15.0", "18.0.1.17.0"):
            caminho = file_path(
                f"l10n_br_hr_payroll/migrations/{versao}/post-migration.py"
            )
            spec = importlib.util.spec_from_file_location("mig168", caminho)
            modulo = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(modulo)
            with self.assertLogs(modulo.__name__, "WARNING") as log:
                modulo.migrate(self.env.cr, "18.0.1.14.0")
            self.assertTrue(
                any(str(contract.id) in linha and "3" in linha for linha in log.output)
            )

    def test_importacao_monthly_com_valor_hora_antigo_zera_o_valor(self):
        """Planilha que traz Monthly junto com o valor da hora antigo."""
        emp = self._create_employee("Importado 168")
        contrato = self.env["hr.contract"].create(
            {
                "name": "Importado",
                "employee_id": emp.id,
                "wage": 3000.0,
                "date_start": "2024-01-01",
                "state": "open",
                "struct_id": self.structure_clt.id,
                "company_id": self.env.company.id,
                "salary_unit": self._unidade_salario("5").id,
                "l10n_br_valor_hora": 20.0,
            }
        )
        self.assertEqual(contrato.l10n_br_valor_hora, 0.0)
        contrato.write(
            {"salary_unit": self._unidade_salario("5").id, "l10n_br_valor_hora": 25.0}
        )
        self.assertEqual(contrato.l10n_br_valor_hora, 0.0)
