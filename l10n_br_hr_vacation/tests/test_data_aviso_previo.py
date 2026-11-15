# Copyright 2026 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""TG-137: data da concessão do aviso prévio na rescisão (``dtAvPrv`` do S-2299)."""

from datetime import date

from odoo.exceptions import ValidationError
from odoo.tests import tagged

from .common import VacationCommon


@tagged("post_install", "-at_install")
class TestDataAvisoPrevio(VacationCommon):
    def _rescisao(self, **extra):
        emp = self._create_employee("Aviso Prévio")
        contract = self._create_contract(emp, wage=3000.00, date_start=date(2020, 1, 1))
        vals = {
            "name": "Rescisão",
            "employee_id": emp.id,
            "contract_id": contract.id,
            "date_from": date(2026, 11, 1),
            "date_to": date(2026, 11, 30),
            "company_id": self.env.company.id,
        }
        vals.update(extra)
        return self.env["hr.payslip"].create(vals)

    def test_campo_e_opcional(self):
        self.assertFalse(self._rescisao().l10n_br_data_aviso_previo)

    def test_data_entre_admissao_e_fim_da_rescisao(self):
        slip = self._rescisao(l10n_br_data_aviso_previo=date(2026, 10, 30))
        self.assertEqual(slip.l10n_br_data_aviso_previo, date(2026, 10, 30))
        slip.l10n_br_data_aviso_previo = date(2026, 11, 30)

    def test_data_depois_do_fim_da_rescisao_recusa(self):
        with self.assertRaisesRegex(ValidationError, "Concessão do Aviso"):
            self._rescisao(l10n_br_data_aviso_previo=date(2026, 12, 1))

    def test_data_antes_da_admissao_recusa(self):
        with self.assertRaisesRegex(ValidationError, "Concessão do Aviso"):
            self._rescisao(l10n_br_data_aviso_previo=date(2019, 12, 31))

    def test_copia_do_holerite_nao_leva_a_data(self):
        slip = self._rescisao(l10n_br_data_aviso_previo=date(2026, 10, 30))
        self.assertNotIn("l10n_br_data_aviso_previo", slip.copy_data()[0])
