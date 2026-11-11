# Copyright 2024 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""TG-84: o desconto de DSR por falta é por semana com falta (Lei 605/49, art. 6º)."""

from datetime import date
from unittest import mock

from odoo.exceptions import ValidationError
from odoo.tests.common import TransactionCase

from odoo.addons.l10n_br_hr_payroll.models.salary_rules_br import (
    inicio_semana,
    semanas_com_falta,
)

from .common import PayrollCommon


class TestSemanasComFaltaPuro(TransactionCase):
    """Contagem pura de semanas com falta."""

    def test_inicio_semana_e_segunda(self):
        self.assertEqual(inicio_semana(date(2024, 3, 3)), date(2024, 2, 26))
        self.assertEqual(inicio_semana(date(2024, 3, 4)), date(2024, 3, 4))

    def test_uma_falta(self):
        self.assertEqual(semanas_com_falta([date(2024, 3, 6)]), 1)

    def test_duas_faltas_na_mesma_semana(self):
        self.assertEqual(semanas_com_falta([date(2024, 3, 4), date(2024, 3, 9)]), 1)

    def test_faltas_em_semanas_diferentes(self):
        self.assertEqual(semanas_com_falta([date(2024, 3, 4), date(2024, 3, 12)]), 2)

    def test_domingo_fecha_a_semana_anterior(self):
        self.assertEqual(semanas_com_falta([date(2024, 3, 3), date(2024, 3, 4)]), 2)

    def test_falta_sem_data_conta_numa_semana_propria(self):
        self.assertEqual(semanas_com_falta([], 2), 2)
        self.assertEqual(semanas_com_falta([date(2024, 3, 4)], 1), 2)


class TestDsrPorSemana(PayrollCommon):
    """Holerite: DESC_DSR = salário/30 por semana com falta."""

    def _holerite(self, faltas, datas=(), contract=None, **periodo):
        if contract is None:
            emp = self._create_employee()
            contract = self._create_contract(emp, wage=3000.00)
        slip = self._create_payslip(contract.employee_id, contract, **periodo)
        slip.write(
            {
                "l10n_br_faltas_injustificadas": faltas,
                "l10n_br_falta_ids": [(0, 0, {"date": d}) for d in datas],
            }
        )
        slip.compute_sheet()
        return slip

    def test_uma_falta_desconta_um_repouso(self):
        slip = self._holerite(1, [date(2024, 3, 6)])
        self.assertAlmostEqualMoney(self._get_line_total(slip, "FALTAS"), 100.00)
        self.assertAlmostEqualMoney(self._get_line_total(slip, "DESC_DSR"), 100.00)

    def test_duas_faltas_na_mesma_semana_descontam_um_dsr(self):
        slip = self._holerite(2, [date(2024, 3, 4), date(2024, 3, 6)])
        self.assertAlmostEqualMoney(self._get_line_total(slip, "FALTAS"), 200.00)
        self.assertAlmostEqualMoney(self._get_line_total(slip, "DESC_DSR"), 100.00)

    def test_faltas_em_semanas_diferentes_descontam_um_dsr_cada(self):
        slip = self._holerite(2, [date(2024, 3, 4), date(2024, 3, 12)])
        self.assertAlmostEqualMoney(self._get_line_total(slip, "DESC_DSR"), 200.00)

    def test_faltas_sem_data_valem_uma_semana_cada(self):
        """Compatível com a carga da POC, que só informa a contagem."""
        slip = self._holerite(2)
        self.assertAlmostEqualMoney(self._get_line_total(slip, "DESC_DSR"), 200.00)

    def test_misto_com_e_sem_data(self):
        slip = self._holerite(3, [date(2024, 3, 4), date(2024, 3, 5)])
        self.assertAlmostEqualMoney(self._get_line_total(slip, "DESC_DSR"), 200.00)

    def test_sem_falta_nao_desconta_dsr(self):
        """Falta justificada não entra na contagem, logo não há desconto."""
        slip = self._holerite(0)
        self.assertFalse(slip.line_ids.filtered(lambda r: r.code == "DESC_DSR"))

    def test_semana_atravessando_o_mes_desconta_uma_vez(self):
        """29/02 (qui) e 01/03 (sex) são a mesma semana: um repouso só."""
        emp = self._create_employee()
        contract = self._create_contract(emp, wage=3000.00)
        fev = self._holerite(
            1,
            [date(2024, 2, 29)],
            contract=contract,
            date_from=date(2024, 2, 1),
            date_to=date(2024, 2, 29),
        )
        mar = self._holerite(1, [date(2024, 3, 1)], contract=contract)
        self.assertAlmostEqualMoney(self._get_line_total(fev, "DESC_DSR"), 100.00)
        self.assertAlmostEqualMoney(self._get_line_total(mar, "DESC_DSR"), 0.0)
        # O salário, em contrapartida, perde as duas faltas.
        self.assertAlmostEqualMoney(self._get_line_total(mar, "FALTAS"), 100.00)

    def test_semana_atravessando_o_mes_calculada_fora_de_ordem(self):
        """O repouso fica com o holerite da primeira falta, em qualquer ordem."""
        emp = self._create_employee()
        contract = self._create_contract(emp, wage=3000.00)
        mar = self._holerite(1, [date(2024, 3, 1)], contract=contract)
        fev = self._holerite(
            1,
            [date(2024, 2, 29)],
            contract=contract,
            date_from=date(2024, 2, 1),
            date_to=date(2024, 2, 29),
        )
        mar.compute_sheet()
        self.assertAlmostEqualMoney(self._get_line_total(fev, "DESC_DSR"), 100.00)
        self.assertAlmostEqualMoney(self._get_line_total(mar, "DESC_DSR"), 0.0)

    def test_falta_em_ferias_gozadas_nao_perde_dsr(self):
        emp = self._create_employee()
        contract = self._create_contract(emp, wage=3000.00)
        slip = self._create_payslip(emp, contract)
        slip.write(
            {
                "l10n_br_faltas_injustificadas": 2,
                "l10n_br_falta_ids": [(0, 0, {"date": date(2024, 3, 5)})],
            }
        )
        with mock.patch.object(
            type(slip),
            "_l10n_br_ferias_gozadas",
            return_value=[(date(2024, 3, 4), date(2024, 3, 8))],
        ):
            slip.compute_sheet()
        # A data cai nas férias (fica de fora); a outra falta, sem data, conta.
        self.assertAlmostEqualMoney(self._get_line_total(slip, "DESC_DSR"), 100.00)

    def test_admissao_no_meio_da_semana(self):
        emp = self._create_employee()
        contract = self._create_contract(
            emp, wage=3000.00, date_start=date(2024, 3, 13)
        )
        slip = self._holerite(1, [date(2024, 3, 14)], contract=contract)
        self.assertAlmostEqualMoney(self._get_line_total(slip, "DESC_DSR"), 100.00)

    def test_falta_em_semana_com_feriado_perde_um_repouso(self):
        """A semana do feriado de 29/03/2024 (sex): um repouso, como as demais."""
        slip = self._holerite(1, [date(2024, 3, 27)])
        self.assertAlmostEqualMoney(self._get_line_total(slip, "DESC_DSR"), 100.00)

    def test_data_fora_do_periodo_e_recusada(self):
        emp = self._create_employee()
        contract = self._create_contract(emp, wage=3000.00)
        slip = self._create_payslip(emp, contract)
        with self.assertRaises(ValidationError):
            slip.write(
                {
                    "l10n_br_faltas_injustificadas": 1,
                    "l10n_br_falta_ids": [(0, 0, {"date": date(2024, 4, 2)})],
                }
            )

    def test_mais_datas_que_faltas_e_recusado(self):
        emp = self._create_employee()
        contract = self._create_contract(emp, wage=3000.00)
        slip = self._create_payslip(emp, contract)
        with self.assertRaises(ValidationError):
            slip.write(
                {
                    "l10n_br_faltas_injustificadas": 1,
                    "l10n_br_falta_ids": [
                        (0, 0, {"date": date(2024, 3, 4)}),
                        (0, 0, {"date": date(2024, 3, 12)}),
                    ],
                }
            )
