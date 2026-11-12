# Copyright 2024 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""TG-90: holerite confirmado pode ser estornado, com rastro, sem contar em dobro."""

from datetime import date

from odoo.exceptions import UserError

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

    def test_par_fica_fora_de_vigor_enquanto_o_estorno_existe(self):
        emp = self._create_employee()
        contract = self._create_contract(emp, wage=3000.00)
        original = self._confirmado(contract)
        self.assertFalse(original.l10n_br_fora_de_vigor)
        estorno = self._estornar(original)
        self.assertTrue(original.l10n_br_fora_de_vigor)
        self.assertTrue(estorno.l10n_br_fora_de_vigor)

    def test_estorno_nao_pode_ser_cancelado(self):
        """TG-90#P2: nem pela ação, nem pela gravação do estado, nem liberado."""
        self.env["ir.config_parameter"].sudo().set_param(
            "payroll.allow_cancel_payslips", "True"
        )
        emp = self._create_employee()
        contract = self._create_contract(emp, wage=3000.00)
        original = self._confirmado(contract)
        estorno = self._estornar(original)
        with self.assertRaises(UserError):
            estorno.action_payslip_cancel()
        with self.assertRaises(UserError):
            estorno.write({"state": "cancel"})
        self.assertEqual(estorno.state, "done")
        self.assertTrue(original.l10n_br_fora_de_vigor)
        # O holerite comum continua cancelável com a opção ligada.
        outro = self._confirmado(contract, de=date(2024, 4, 1), ate=date(2024, 4, 30))
        outro.action_payslip_cancel()
        self.assertEqual(outro.state, "cancel")

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

    def test_duplicar_o_estornado_gera_holerite_comum(self):
        """ "Duplicar" não leva o vínculo do estorno: a cópia vale."""
        emp = self._create_employee()
        contract = self._create_contract(emp, wage=3000.00)
        original = self._confirmado(contract)
        self._estornar(original)
        copia = original.copy()
        self.assertFalse(copia.refunded_id)
        self.assertFalse(copia.credit_note)
        self.assertFalse(copia.l10n_br_fora_de_vigor)

    def test_duplicar_o_estorno_nao_gera_estorno(self):
        emp = self._create_employee()
        contract = self._create_contract(emp, wage=3000.00)
        estorno = self._estornar(self._confirmado(contract))
        copia = estorno.copy()
        self.assertFalse(copia.credit_note)
        self.assertFalse(copia.l10n_br_estorno)
        self.assertFalse(copia.l10n_br_fora_de_vigor)

    def test_devolucao_repetida_e_recusada(self):
        emp = self._create_employee()
        contract = self._create_contract(emp, wage=3000.00)
        original = self._confirmado(contract)
        estorno = self._estornar(original)
        with self.assertRaises(UserError):
            original.refund_sheet()
        self.assertEqual(original.refunded_id, estorno)

    def test_estornar_o_estorno_e_recusado(self):
        emp = self._create_employee()
        contract = self._create_contract(emp, wage=3000.00)
        estorno = self._estornar(self._confirmado(contract))
        with self.assertRaises(UserError):
            estorno.refund_sheet()
        self.assertFalse(estorno.refunded_id)

    def test_rascunho_com_credit_note_marcado_continua_em_vigor(self):
        emp = self._create_employee()
        contract = self._create_contract(emp, wage=3000.00)
        slip = self._create_payslip(emp, contract)
        slip.write({"credit_note": True})
        self.assertFalse(slip.l10n_br_fora_de_vigor)
