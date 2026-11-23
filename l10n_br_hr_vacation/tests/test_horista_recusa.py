# Copyright 2026 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""TG-166: férias, 13º e rescisão do horista são recusados, não calculados errado."""

from datetime import date

from odoo.exceptions import UserError

from .common import VacationCommon


class TestHoristaRecusa(VacationCommon):
    def _slip(self, estrutura, horista):
        emp = self._create_employee()
        contract = self._create_contract(emp, wage=20.0, structure=estrutura)
        if horista:
            contract.write(
                {"l10n_br_unidade_salario": "hora", "l10n_br_valor_hora": 20.0}
            )
        return self.env["hr.payslip"].create(
            {
                "name": "Verba",
                "employee_id": emp.id,
                "contract_id": contract.id,
                "struct_id": estrutura.id,
                "date_from": date(2026, 10, 1),
                "date_to": date(2026, 10, 31),
                "company_id": self.env.company.id,
            }
        )

    def test_recusa_ferias_13_e_rescisao_do_horista(self):
        for estrutura in (
            self.structure_ferias,
            self.structure_13_primeira,
            self.structure_13_segunda,
            self.structure_13,
            self.structure_rescisao,
        ):
            slip = self._slip(estrutura, horista=True)
            with self.assertRaisesRegex(UserError, "horista"):
                slip.compute_sheet()

    def test_mensal_do_horista_nao_e_recusado(self):
        slip = self._slip(self.structure_clt, horista=True)
        slip.l10n_br_horas_pagas = 100.0
        slip.compute_sheet()
        self.assertTrue(slip.line_ids)

    def test_mensalista_nao_e_recusado(self):
        slip = self._slip(self.structure_ferias, horista=False)
        slip._l10n_br_exigir_sem_horista()
