# Copyright 2024 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""TG-127: criar o recibo de férias reconcilia o DSR dos outros holerites.

Sem mock: recibo de férias real, só ações padrão (criar, calcular, confirmar,
cancelar). Caso da revisão r2 da TG-84 (N1): falta em 30/11/2026 e 02/12/2026,
na mesma semana (30/11 a 06/12).
"""
from datetime import date

from odoo.exceptions import UserError
from odoo.tests import tagged

from .common import VacationCommon

NOV = (date(2026, 11, 1), date(2026, 11, 30))
DEZ = (date(2026, 12, 1), date(2026, 12, 31))


@tagged("post_install", "-at_install")
class TestDsrFerias(VacationCommon):
    def _contrato(self):
        emp = self._create_employee()
        return emp, self._create_contract(emp, wage=3600.0, date_start=date(2024, 1, 2))

    def _mensal(self, emp, contract, periodo, dia):
        slip = self._create_payslip(emp, contract, *periodo)
        slip.write(
            {
                "l10n_br_faltas_injustificadas": 1,
                "l10n_br_falta_ids": [(0, 0, {"date": dia})],
            }
        )
        slip.compute_sheet()
        return slip

    def _recibo(self, emp, contract, inicio, fim, dias_gozo):
        alloc = self.env["hr.leave.allocation"].create(
            {
                "employee_id": emp.id,
                "holiday_status_id": self.leave_type_ferias.id,
                "date_from": date(2025, 1, 2),
                "date_to": date(2026, 1, 1),
            }
        )
        alloc.action_validate()
        return self.env["hr.payslip"].create(
            {
                "name": "Férias %s" % inicio,
                "employee_id": emp.id,
                "contract_id": contract.id,
                "struct_id": self.structure_ferias.id,
                "date_from": inicio,
                "date_to": fim,
                "l10n_br_ferias_allocation_id": alloc.id,
                "l10n_br_dias_periodo_gozado": dias_gozo,
                "company_id": self.env.company.id,
            }
        )

    def _dsr(self, slip):
        return self._get_line_total(slip, "DESC_DSR")

    def _dois_meses(self):
        emp, contract = self._contrato()
        nov = self._mensal(emp, contract, NOV, date(2026, 11, 30))
        dez = self._mensal(emp, contract, DEZ, date(2026, 12, 2))
        # Novembro tem a primeira falta da semana: dezembro não desconta.
        self.assertAlmostEqualMoney(self._dsr(nov), 120.00)
        self.assertAlmostEqualMoney(self._dsr(dez), 0.0)
        return emp, contract, nov, dez

    def test_criar_recibo_que_cobre_a_falta_recalcula_o_mes_seguinte(self):
        emp, contract, nov, dez = self._dois_meses()
        recibo = self._recibo(emp, contract, date(2026, 11, 21), NOV[1], 10)
        # A falta de 30/11 cai nas férias: o repouso passa a ser de dezembro.
        self.assertAlmostEqualMoney(self._dsr(nov), 0.0)
        self.assertAlmostEqualMoney(self._dsr(dez), 120.00)
        recibo.compute_sheet()
        self.assertAlmostEqualMoney(self._dsr(dez), 120.00)
        # Cancelar o recibo devolve o repouso a novembro.
        recibo.action_payslip_cancel()
        self.assertAlmostEqualMoney(self._dsr(nov), 120.00)
        self.assertAlmostEqualMoney(self._dsr(dez), 0.0)

    def test_criar_recibo_com_mes_seguinte_confirmado_e_recusado(self):
        emp, contract, nov, dez = self._dois_meses()
        dez.action_payslip_done()
        with self.assertRaises(UserError):
            self._recibo(emp, contract, date(2026, 11, 21), NOV[1], 10)
        self.assertFalse(
            self.env["hr.payslip"].search(
                [
                    ("contract_id", "=", contract.id),
                    ("struct_id", "=", self.structure_ferias.id),
                ]
            )
        )
        self.assertAlmostEqualMoney(self._dsr(nov), 120.00)
        self.assertAlmostEqualMoney(self._dsr(dez), 0.0)

    def test_recibo_que_nao_cobre_falta_nao_mexe_no_confirmado(self):
        emp, contract, nov, dez = self._dois_meses()
        dez.action_payslip_done()
        self._recibo(emp, contract, date(2026, 11, 9), date(2026, 11, 18), 10)
        self.assertEqual(dez.state, "done")
        self.assertAlmostEqualMoney(self._dsr(dez), 0.0)
        self.assertAlmostEqualMoney(self._dsr(nov), 120.00)
