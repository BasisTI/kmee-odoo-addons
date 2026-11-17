# Copyright 2026 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""TG-152: a função única da competência de cada parte do recibo de férias."""

from datetime import date

from .common import PayrollCommon


class TestCompetenciasFerias(PayrollCommon):
    def _slip(self, codigo, de, ate):
        emp = self._create_employee()
        contract = self._create_contract(emp, date_start=date(2020, 1, 1))
        estrutura = self.env["hr.payroll.structure"].search(
            [("code", "=", codigo)], limit=1
        ) or self.env["hr.payroll.structure"].create({"name": codigo, "code": codigo})
        return self.env["hr.payslip"].create(
            {
                "name": "t",
                "employee_id": emp.id,
                "contract_id": contract.id,
                "struct_id": estrutura.id,
                "date_from": de,
                "date_to": ate,
            }
        )

    def test_ferias_no_mes(self):
        slip = self._slip("FERIAS", date(2026, 11, 2), date(2026, 11, 21))
        self.assertEqual(slip._l10n_br_competencias_ferias(), [("2026-11", 20)])

    def test_ferias_atravessam_o_mes(self):
        slip = self._slip("FERIAS", date(2026, 11, 20), date(2026, 12, 18))
        self.assertEqual(
            slip._l10n_br_competencias_ferias(), [("2026-11", 11), ("2026-12", 18)]
        )

    def test_ferias_atravessam_o_ano(self):
        slip = self._slip("FERIAS", date(2026, 12, 20), date(2027, 1, 18))
        self.assertEqual(
            slip._l10n_br_competencias_ferias(), [("2026-12", 12), ("2027-01", 18)]
        )

    def test_nao_ferias_fica_inteiro_no_mes_de_date_from(self):
        slip = self._slip("OUTRA_T152", date(2026, 11, 20), date(2026, 12, 18))
        self.assertEqual(slip._l10n_br_competencias_ferias(), [("2026-11", 0)])
        self.assertEqual(slip._l10n_br_ratear_valor(100.0, "2026-12"), 100.0)

    def test_ratear_soma_bate_ao_centavo(self):
        slip = self._slip("FERIAS", date(2026, 10, 20), date(2026, 12, 5))
        for valor in (1000.01, 0.07, 3333.33, 12345.67):
            partes = [
                slip._l10n_br_ratear_valor(valor, c)
                for c in ("2026-10", "2026-11", "2026-12")
            ]
            self.assertAlmostEqual(sum(partes), valor, places=2)
            self.assertEqual(slip._l10n_br_ratear_valor(valor, "2027-01"), 0.0)

    def test_abono_vai_inteiro_na_primeira_competencia(self):
        slip = self._slip("FERIAS", date(2026, 11, 20), date(2026, 12, 18))
        self.assertEqual(
            slip._l10n_br_ratear_valor(500.0, "2026-11", "ABONO_PECUNIARIO"), 500.0
        )
        self.assertEqual(
            slip._l10n_br_ratear_valor(500.0, "2026-12", "ADICIONAL_ABONO"), 0.0
        )
