# Copyright 2024 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""TG-84: o desconto de DSR por falta é por semana com falta (Lei 605/49, art. 6º)."""

from datetime import date
from unittest import mock

from odoo.exceptions import UserError, ValidationError
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
        # Sem recalcular à mão: lançar a falta de fevereiro reconcilia o março.
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

    def _dois_meses(self):
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
        return fev, mar

    def test_apagar_a_falta_anterior_devolve_o_repouso_ao_outro_mes(self):
        fev, mar = self._dois_meses()
        self.assertAlmostEqualMoney(self._get_line_total(mar, "DESC_DSR"), 0.0)
        fev.l10n_br_falta_ids.unlink()
        self.assertAlmostEqualMoney(self._get_line_total(mar, "DESC_DSR"), 100.00)

    def test_cancelar_o_holerite_anterior_devolve_o_repouso(self):
        fev, mar = self._dois_meses()
        fev.write({"state": "cancel"})
        self.assertAlmostEqualMoney(self._get_line_total(mar, "DESC_DSR"), 100.00)

    def test_excluir_o_holerite_anterior_devolve_o_repouso(self):
        fev, mar = self._dois_meses()
        fev.write({"state": "draft"})  # o payroll só exclui rascunho
        fev.unlink()
        self.assertAlmostEqualMoney(self._get_line_total(mar, "DESC_DSR"), 100.00)

    def test_holerite_confirmado_dependente_recusa_a_alteracao(self):
        emp = self._create_employee()
        contract = self._create_contract(emp, wage=3000.00)
        mar = self._holerite(1, [date(2024, 3, 1)], contract=contract)
        mar.write({"state": "done"})
        fev = self._holerite(
            0,
            contract=contract,
            date_from=date(2024, 2, 1),
            date_to=date(2024, 2, 29),
        )
        with self.assertRaises(UserError):
            fev.write(
                {
                    "l10n_br_faltas_injustificadas": 1,
                    "l10n_br_falta_ids": [(0, 0, {"date": date(2024, 2, 29)})],
                }
            )

    # ------------------------------------------------------------------
    # r2: ponto único por comparação antes/depois e variantes da revisão
    # ------------------------------------------------------------------

    def test_trocar_empregado_do_holerite_reconcilia_o_outro_mes(self):
        """G1: o outro mês volta a descontar a semana do empregado antigo."""
        fev, mar = self._dois_meses()
        emp2 = self._create_employee(name="Outro")
        contract2 = self._create_contract(emp2, wage=3000.00)
        fev.write({"employee_id": emp2.id, "contract_id": contract2.id})
        self.assertAlmostEqualMoney(self._get_line_total(mar, "DESC_DSR"), 100.00)

    def test_mudar_o_periodo_nao_deixa_falta_fora_dele(self):
        """G2: a falta de 29/02 não cabe num holerite de janeiro."""
        fev, _mar = self._dois_meses()
        with self.assertRaises(ValidationError):
            fev.write({"date_from": date(2024, 1, 1), "date_to": date(2024, 1, 31)})

    def test_falta_do_mes_anterior_em_ferias_nao_bloqueia_o_seguinte(self):
        """G4: a falta que cai em férias não é falta, nem para o mês seguinte."""
        emp = self._create_employee()
        contract = self._create_contract(emp, wage=3000.00)
        ferias = [(date(2024, 2, 26), date(2024, 2, 29))]
        with mock.patch.object(
            type(self.env["hr.payslip"]), "_l10n_br_ferias_gozadas", return_value=ferias
        ):
            fev = self._holerite(
                1,
                [date(2024, 2, 29)],
                contract=contract,
                date_from=date(2024, 2, 1),
                date_to=date(2024, 2, 29),
            )
            mar = self._holerite(1, [date(2024, 3, 1)], contract=contract)
        self.assertAlmostEqualMoney(self._get_line_total(fev, "DESC_DSR"), 0.0)
        self.assertAlmostEqualMoney(self._get_line_total(mar, "DESC_DSR"), 100.00)

    def test_segunda_falta_na_mesma_semana_nao_recusa_se_o_outro_nao_muda(self):
        """G9: o março confirmado não depende da 2ª falta de fevereiro."""
        emp = self._create_employee()
        contract = self._create_contract(emp, wage=3000.00)
        fev = self._holerite(
            1,
            [date(2024, 2, 28)],
            contract=contract,
            date_from=date(2024, 2, 1),
            date_to=date(2024, 2, 29),
        )
        mar = self._holerite(1, [date(2024, 3, 1)], contract=contract)
        mar.write({"state": "done"})
        fev.write(
            {
                "l10n_br_faltas_injustificadas": 2,
                "l10n_br_falta_ids": [(0, 0, {"date": date(2024, 2, 29)})],
            }
        )
        self.assertEqual(len(fev.l10n_br_falta_ids), 2)
        self.assertEqual(mar.state, "done")

    def test_rascunho_nunca_calculado_nao_e_calculado_pela_reconciliacao(self):
        emp = self._create_employee()
        contract = self._create_contract(emp, wage=3000.00)
        fev = self._holerite(
            1,
            [date(2024, 2, 28)],
            contract=contract,
            date_from=date(2024, 2, 1),
            date_to=date(2024, 2, 29),
        )
        mar = self.env["hr.payslip"].create(
            {
                "name": "Março",
                "employee_id": emp.id,
                "contract_id": contract.id,
                "struct_id": contract.struct_id.id,
                "date_from": date(2024, 3, 1),
                "date_to": date(2024, 3, 31),
                "company_id": self.env.company.id,
                "l10n_br_faltas_injustificadas": 1,
                "l10n_br_falta_ids": [(0, 0, {"date": date(2024, 3, 1)})],
            }
        )
        fev.write(
            {
                "l10n_br_faltas_injustificadas": 2,
                "l10n_br_falta_ids": [(0, 0, {"date": date(2024, 2, 29)})],
            }
        )
        self.assertEqual(mar.state, "draft")
        self.assertFalse(mar.line_ids)

    def test_falta_criada_direto_no_modelo_respeita_a_contagem(self):
        """M5: sem folga na contagem de faltas, a data nova é recusada."""
        slip = self._holerite(0)
        with self.assertRaises(ValidationError):
            self.env["l10n_br.hr.payslip.falta"].create(
                {"payslip_id": slip.id, "date": date(2024, 3, 5)}
            )

    def test_holerite_confirmado_nao_aceita_falta_nova(self):
        """M7."""
        slip = self._holerite(1, [date(2024, 3, 5)])
        slip.write({"state": "done"})
        with self.assertRaises(UserError):
            slip.write(
                {
                    "l10n_br_faltas_injustificadas": 2,
                    "l10n_br_falta_ids": [(0, 0, {"date": date(2024, 3, 12)})],
                }
            )
        with self.assertRaises(UserError):
            slip.l10n_br_falta_ids.unlink()

    def test_falta_sem_data_nao_passa_das_semanas_do_periodo(self):
        """S1: 5 faltas só por contagem numa semana de período: um repouso."""
        slip = self._holerite(5, date_from=date(2024, 3, 4), date_to=date(2024, 3, 10))
        self.assertAlmostEqualMoney(self._get_line_total(slip, "FALTAS"), 500.00)
        self.assertAlmostEqualMoney(self._get_line_total(slip, "DESC_DSR"), 100.00)

    def test_falta_sem_data_completa_as_semanas_sem_falta_datada(self):
        """Semana com falta datada não recebe também uma falta sem data."""
        slip = self._holerite(
            3,
            [date(2024, 3, 5)],
            date_from=date(2024, 3, 4),
            date_to=date(2024, 3, 17),
        )
        # 2 semanas no período: 1 datada + 1 sem data (a outra sem data não cabe).
        self.assertAlmostEqualMoney(self._get_line_total(slip, "DESC_DSR"), 200.00)

    def test_usuario_sem_acesso_ao_holerite_nao_le_a_falta(self):
        """M6: o acesso à falta segue o acesso ao holerite (multiempresa)."""
        slip = self._holerite(1, [date(2024, 3, 5)])
        outra = self.env["res.company"].create({"name": "Outra empresa"})
        user = self.env["res.users"].create(
            {
                "name": "Gerente de outra empresa",
                "login": "gerente_outra_dsr",
                "company_id": outra.id,
                "company_ids": [(6, 0, [outra.id])],
                "groups_id": [
                    (
                        6,
                        0,
                        [
                            self.env.ref("base.group_user").id,
                            self.env.ref("payroll.group_payroll_manager").id,
                        ],
                    )
                ],
            }
        )
        self.env.flush_all()
        faltas = self.env["l10n_br.hr.payslip.falta"].with_user(user)
        self.assertFalse(faltas.search([("payslip_id", "=", slip.id)]))

    def test_oficial_de_folha_nao_le_falta_de_departamento_alheio(self):
        """M6: o oficial só vê as faltas do que o holerite lhe mostra."""
        emp = self._create_employee()
        contract = self._create_contract(emp, wage=3000.00)
        gerente = self.env["hr.employee"].create(
            {"name": "Chefe", "cnpj_cpf": self._proximo_cpf()}
        )
        depto = self.env["hr.department"].create(
            {"name": "Depto alheio", "manager_id": gerente.id}
        )
        emp.department_id = depto
        slip = self._holerite(1, [date(2024, 3, 5)], contract=contract)
        oficial = self.env["res.users"].create(
            {
                "name": "Oficial de folha",
                "login": "oficial_dsr",
                "groups_id": [
                    (
                        6,
                        0,
                        [
                            self.env.ref("base.group_user").id,
                            self.env.ref("payroll.group_payroll_user").id,
                        ],
                    )
                ],
            }
        )
        self.env.flush_all()
        faltas = self.env["l10n_br.hr.payslip.falta"].with_user(oficial)
        self.assertFalse(faltas.search([("payslip_id", "=", slip.id)]))

    def test_gravar_datas_falta_e_idempotente_e_troca_as_datas(self):
        """Gancho do módulo de ponto: datas e contagem na mesma gravação."""
        slip = self._holerite(2, [date(2024, 3, 4), date(2024, 3, 12)])
        slip._l10n_br_gravar_datas_falta([date(2024, 3, 4), date(2024, 3, 12)], 2)
        self.assertEqual(len(slip.l10n_br_falta_ids), 2)
        # Menos faltas que antes: a contagem cai junto com as datas.
        slip._l10n_br_gravar_datas_falta([date(2024, 3, 12)], 1)
        self.assertEqual(slip.l10n_br_falta_ids.mapped("date"), [date(2024, 3, 12)])
        self.assertEqual(slip.l10n_br_faltas_injustificadas, 1)
        slip.compute_sheet()
        self.assertAlmostEqualMoney(self._get_line_total(slip, "DESC_DSR"), 100.00)
