# Copyright 2024 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""TG-90: holerite confirmado pode ser estornado, com rastro, sem contar em dobro."""

from datetime import date

from .common import PayrollCommon


class TestEstornoHolerite(PayrollCommon):
    def _confirmado(self, contract, de=None, ate=None):
        slip = self._create_payslip(
            contract.employee_id,
            contract,
            date_from=de or date(2024, 3, 1),
            date_to=ate or date(2024, 3, 31),
        )
        slip.action_payslip_done()
        return slip

    def _estornar(self, slip):
        slip.refund_sheet()
        return slip.refunded_id

    def test_estorno_tem_rastro_e_copia_as_linhas(self):
        emp = self._create_employee()
        contract = self._create_contract(emp, wage=3000.00)
        original = self._confirmado(contract)
        estorno = self._estornar(original)
        self.assertTrue(estorno.credit_note)
        self.assertEqual(estorno.state, "done")
        self.assertEqual(original.refunded_id, estorno)
        self.assertEqual(
            sorted(estorno.line_ids.mapped("code")),
            sorted(original.line_ids.mapped("code")),
        )
        self.assertAlmostEqualMoney(
            self._get_line_total(estorno, "NET"), self._get_line_total(original, "NET")
        )

    def test_par_fica_fora_de_vigor_e_volta_se_o_estorno_cancela(self):
        emp = self._create_employee()
        contract = self._create_contract(emp, wage=3000.00)
        original = self._confirmado(contract)
        self.assertFalse(original.l10n_br_fora_de_vigor)
        estorno = self._estornar(original)
        self.assertTrue(original.l10n_br_fora_de_vigor)
        self.assertTrue(estorno.l10n_br_fora_de_vigor)
        estorno.write({"state": "cancel"})
        self.assertFalse(original.l10n_br_fora_de_vigor)

    def test_media_ignora_o_par_estornado(self):
        emp = self._create_employee()
        contract = self._create_contract(emp, wage=3000.00)
        marco = self._confirmado(contract)
        abril = self._create_payslip(
            emp, contract, date_from=date(2024, 4, 1), date_to=date(2024, 4, 30)
        )
        antes = abril._l10n_br_media_habitual(("SALARIO_BASE",))
        self.assertGreater(antes, 0.0)
        self._estornar(marco)
        self.assertEqual(abril._l10n_br_media_habitual(("SALARIO_BASE",)), 0.0)

    def test_salario_pago_ignora_o_par_estornado(self):
        emp = self._create_employee()
        contract = self._create_contract(emp, wage=3000.00)
        marco = self._confirmado(contract)
        # Outra estrutura mensal na mesma competência: lê o salário do primeiro.
        vizinho = self.env["hr.payslip"].create(
            {
                "name": "Vizinho",
                "employee_id": emp.id,
                "contract_id": contract.id,
                "struct_id": self.structure_estatuto.id,
                "date_from": date(2024, 3, 1),
                "date_to": date(2024, 3, 31),
            }
        )
        self.assertGreater(vizinho._l10n_br_salario_pago_mensal(contract), 0.0)
        self._estornar(marco)
        self.assertEqual(vizinho._l10n_br_salario_pago_mensal(contract), 0.0)

    def test_dsr_do_dependente_aberto_recalcula_ao_estornar(self):
        """Estornar o holerite que tem a falta da semana muda o DSR do vizinho."""
        emp = self._create_employee()
        contract = self._create_contract(emp, wage=3000.00)
        # Semana de 26/02 a 03/03 cruza o mês; a falta de 29/02 é do holerite de
        # fevereiro (anterior), que é o dono da semana.
        fev = self._create_payslip(
            emp, contract, date_from=date(2024, 2, 1), date_to=date(2024, 2, 29)
        )
        fev.write(
            {
                "l10n_br_faltas_injustificadas": 1,
                "l10n_br_falta_ids": [(0, 0, {"date": date(2024, 2, 28)})],
            }
        )
        fev.compute_sheet()
        mar = self._create_payslip(
            emp, contract, date_from=date(2024, 3, 1), date_to=date(2024, 3, 31)
        )
        mar.write(
            {
                "l10n_br_faltas_injustificadas": 1,
                "l10n_br_falta_ids": [(0, 0, {"date": date(2024, 3, 1)})],
            }
        )
        mar.compute_sheet()
        # Fevereiro é dono da semana (28/02 e 01/03 estão na mesma semana).
        self.assertEqual(self._get_line_total(mar, "DESC_DSR"), 0.0)
        fev.action_payslip_done()
        self._estornar(fev)
        self.assertGreater(abs(self._get_line_total(mar, "DESC_DSR")), 0.0)
