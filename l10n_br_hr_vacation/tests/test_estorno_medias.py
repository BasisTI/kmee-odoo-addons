# Copyright 2024 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""TG-90: o estorno de um mensal mexe na média dos holerites que a leem."""

from datetime import date

from dateutil.relativedelta import relativedelta

from odoo.exceptions import UserError
from odoo.tests import tagged

from .common import VacationCommon


@tagged("post_install", "-at_install")
class TestEstornoMedias(VacationCommon):
    def _mensal_done(self, emp, contract, mes, he_50):
        slip = self.env["hr.payslip"].create(
            {
                "name": f"Mensal {mes}/2024",
                "employee_id": emp.id,
                "contract_id": contract.id,
                "struct_id": self.structure_clt.id,
                "date_from": date(2024, mes, 1),
                "date_to": date(2024, mes, 1) + relativedelta(day=31),
                "l10n_br_horas_extras_50": he_50,
                "company_id": self.env.company.id,
            }
        )
        slip.compute_sheet()
        slip.action_payslip_done()
        return slip

    def _ferias(self, emp, contract):
        slip = self.env["hr.payslip"].create(
            {
                "name": "Férias",
                "employee_id": emp.id,
                "contract_id": contract.id,
                "struct_id": self.structure_ferias.id,
                "date_from": date(2024, 4, 1),
                "date_to": date(2024, 4, 30),
                "company_id": self.env.company.id,
            }
        )
        slip.compute_sheet()
        return slip

    def _cenario(self):
        emp = self._create_employee()
        contract = self._create_contract(emp, wage=3000.00, date_start=date(2024, 1, 1))
        janeiro = self._mensal_done(emp, contract, 1, 30.0)
        self._mensal_done(emp, contract, 2, 5.0)
        self._mensal_done(emp, contract, 3, 5.0)
        return emp, contract, janeiro

    def test_ferias_aberta_recalcula_a_media_ao_estornar(self):
        emp, contract, janeiro = self._cenario()
        ferias = self._ferias(emp, contract)
        antes = self._get_line_total(ferias, "FERIAS")
        janeiro.refund_sheet()
        depois = self._get_line_total(ferias, "FERIAS")
        self.assertLess(depois, antes, "a média sem o mês estornado é menor")

    def test_ferias_confirmada_recusa_o_estorno(self):
        emp, contract, janeiro = self._cenario()
        ferias = self._ferias(emp, contract)
        ferias.action_payslip_done()
        with self.assertRaises(UserError):
            janeiro.refund_sheet()
        self.assertFalse(janeiro.refunded_id)

    def test_par_estornado_fica_fora_da_participacao(self):
        emp, contract, janeiro = self._cenario()
        estorno = janeiro.refund_sheet() and janeiro.refunded_id
        self.assertEqual(janeiro._l10n_br_participacao()[janeiro.id][3], 0)
        self.assertEqual(estorno._l10n_br_participacao()[estorno.id][3], 0)
