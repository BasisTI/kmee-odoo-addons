# Copyright 2026 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""TG-130: Menores da revisão r2 da TG-128 (marca e percentual do noturno)."""
from datetime import date

from odoo.exceptions import ValidationError
from odoo.tests import Form, tagged

from .common import PayrollCommon


@tagged("post_install", "-at_install")
class TestHoraReduzidaContrato(PayrollCommon):
    def _contrato(self, **vals):
        emp = self._create_employee()
        contract = self._create_contract(emp, wage=3500.0)
        contract.write(vals)
        return emp, contract

    def _rascunho(self, emp, contract):
        return self.env["hr.payslip"].create(
            {
                "name": "Rascunho",
                "employee_id": emp.id,
                "contract_id": contract.id,
                "struct_id": self.structure_clt.id,
                "date_from": date(2026, 3, 1),
                "date_to": date(2026, 3, 31),
                "company_id": self.env.company.id,
            }
        )

    # N1: trocar o contrato do rascunho leva a marca do contrato novo
    def test_trocar_contrato_no_write_leva_a_marca_do_novo(self):
        emp, antigo = self._contrato(l10n_br_hora_noturna_reduzida=True)
        slip = self._rascunho(emp, antigo)
        self.assertTrue(slip.l10n_br_usar_hora_reduzida)
        novo = antigo.copy({"l10n_br_hora_noturna_reduzida": False})
        slip.write({"contract_id": novo.id})
        self.assertFalse(slip.l10n_br_usar_hora_reduzida)

    def test_trocar_contrato_no_formulario_grava_a_marca_do_novo(self):
        emp, antigo = self._contrato(l10n_br_hora_noturna_reduzida=True)
        slip = self._rascunho(emp, antigo)
        novo = antigo.copy({"l10n_br_hora_noturna_reduzida": False})
        with Form(slip) as form:
            form.contract_id = novo
        self.assertFalse(slip.l10n_br_usar_hora_reduzida)

    def test_trocar_contrato_do_confirmado_nao_muda_a_marca(self):
        emp, antigo = self._contrato(l10n_br_hora_noturna_reduzida=True)
        slip = self._rascunho(emp, antigo)
        slip.compute_sheet()
        slip.action_payslip_done()
        novo = antigo.copy({"l10n_br_hora_noturna_reduzida": False})
        slip.write({"contract_id": novo.id})
        self.assertTrue(slip.l10n_br_usar_hora_reduzida)

    # N2: gerente de contratos sem acesso à folha
    def test_gerente_de_contratos_sem_folha_altera_a_marca(self):
        emp, contract = self._contrato(l10n_br_hora_noturna_reduzida=True)
        slip = self._rascunho(emp, contract)
        gerente = self.env["res.users"].create(
            {
                "name": "Gerente de contratos",
                "login": "gerente_contratos_tg130",
                "groups_id": [
                    (
                        6,
                        0,
                        [
                            self.env.ref("base.group_user").id,
                            self.env.ref("hr_contract.group_hr_contract_manager").id,
                        ],
                    )
                ],
            }
        )
        contract.with_user(gerente).write({"l10n_br_hora_noturna_reduzida": False})
        self.assertFalse(slip.l10n_br_usar_hora_reduzida)

    # N3: percentual entre 0 (exclusive) e 100
    def test_percentual_do_noturno_fora_do_limite_e_recusado(self):
        _emp, contract = self._contrato()
        for invalido in (0.0, -35.0, 100.01, 250.0):
            with self.assertRaises(ValidationError):
                contract.l10n_br_adicional_noturno_perc = invalido
        for valido in (0.5, 20.0, 25.0, 100.0):
            contract.l10n_br_adicional_noturno_perc = valido
            self.assertEqual(contract.l10n_br_adicional_noturno_perc, valido)
