# Copyright 2024 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""CCT ligada ao contrato e lida pelas regras na competência do holerite (TG-109)."""
from datetime import date

from odoo.exceptions import UserError, ValidationError

from odoo.addons.l10n_br_hr_payroll.tests.common import PayrollCommon


class TestCctContrato(PayrollCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Partner = cls.env["res.partner"]
        cls.sindicato = Partner.create(
            {"name": "Sindicato A", "union_entity_code": "SA1", "is_company": True}
        )
        cls.outro_sindicato = Partner.create(
            {"name": "Sindicato B", "union_entity_code": "SB1", "is_company": True}
        )
        Cct = cls.env["l10n.br.hr.collective.convention"]
        cls.cct1 = Cct.create(
            {
                "name": "CCT 1",
                "partner_union_id": cls.sindicato.id,
                "date_start": date(2026, 1, 1),
                "date_end": date(2026, 5, 31),
                "assistencial_amount": 35.0,
                "monthly_fee_amount": 15.0,
                "vt_employee_pct": 6.0,
                "assistencial_sindicalizado": "half",
            }
        )
        cls.cct2 = Cct.create(
            {
                "name": "CCT 2",
                "partner_union_id": cls.sindicato.id,
                "date_start": date(2026, 6, 1),
                "date_end": date(2026, 12, 31),
                "assistencial_amount": 45.0,
                "monthly_fee_amount": 35.0,
                "vt_employee_pct": 5.0,
                "assistencial_sindicalizado": "zero",
            }
        )
        cls.regra = cls.env["hr.salary.rule"].create(
            {
                "name": "Teste CCT",
                "code": "TESTE_CCT",
                "sequence": 220,
                "category_id": cls.env.ref(
                    "l10n_br_hr_payroll.hr_salary_rule_category_info"
                ).id,
                "condition_select": "none",
                "amount_select": "code",
                "amount_python_compute": (
                    "cct = tools.br.cct(contract)\n"
                    "result = cct.assistencial_amount if cct else -1.0"
                ),
            }
        )
        cls.structure_clt.write({"rule_ids": [(4, cls.regra.id)]})

    def setUp(self):
        super().setUp()
        self.empregado = self._create_employee("Empregado CCT")
        self.contrato = self._create_contract(self.empregado)

    def _holerite(self, contrato, mes, calcular=True, ano=2026, dias=(1, 28)):
        slip = self.env["hr.payslip"].create(
            {
                "name": f"Holerite {mes}/{ano}",
                "employee_id": contrato.employee_id.id,
                "contract_id": contrato.id,
                "struct_id": contrato.struct_id.id,
                "date_from": date(ano, mes, dias[0]),
                "date_to": date(ano, mes, dias[1]),
                "company_id": self.env.company.id,
            }
        )
        if calcular:
            slip.compute_sheet()
        return slip

    def test_contrato_aponta_a_cct_e_herda_o_sindicato(self):
        self.contrato.l10n_br_cct_id = self.cct1
        self.assertEqual(self.contrato.partner_union, self.sindicato)

    def test_cct_de_outro_sindicato_e_recusada(self):
        self.contrato.partner_union = self.outro_sindicato
        with self.assertRaises(ValidationError):
            self.contrato.l10n_br_cct_id = self.cct1

    def test_vigencias_do_mesmo_sindicato_nao_se_sobrepoem(self):
        with self.assertRaises(ValidationError):
            self.env["l10n.br.hr.collective.convention"].create(
                {
                    "name": "CCT sobreposta",
                    "partner_union_id": self.sindicato.id,
                    "date_start": date(2026, 5, 1),
                    "date_end": date(2026, 8, 31),
                }
            )

    def test_cct_vigente_na_competencia_com_troca_no_meio_do_ano(self):
        self.contrato.l10n_br_cct_id = self.cct1
        self.assertEqual(
            self.contrato._l10n_br_cct_vigente(date(2026, 3, 31)), self.cct1
        )
        self.assertEqual(
            self.contrato._l10n_br_cct_vigente(date(2026, 6, 1)), self.cct2
        )
        # Depois da última vigência vale a última vencida (com aviso no holerite).
        self.assertEqual(
            self.contrato._l10n_br_cct_vigente(date(2027, 1, 31)), self.cct2
        )

    def test_contrato_sem_cct_preserva_o_comportamento(self):
        self.assertFalse(self.contrato._l10n_br_cct_vigente(date(2026, 3, 31)))
        slip = self._holerite(self.contrato, 3)
        self.assertAlmostEqualMoney(self._get_line_total(slip, "TESTE_CCT"), -1.0)

    def test_regra_le_a_cct_da_competencia(self):
        self.contrato.l10n_br_cct_id = self.cct1
        marco = self._holerite(self.contrato, 3)
        julho = self._holerite(self.contrato, 7)
        self.assertAlmostEqualMoney(self._get_line_total(marco, "TESTE_CCT"), 35.0)
        self.assertAlmostEqualMoney(self._get_line_total(julho, "TESTE_CCT"), 45.0)

    def test_sindicato_diferente_por_contrato(self):
        outra_cct = self.env["l10n.br.hr.collective.convention"].create(
            {
                "name": "CCT B",
                "partner_union_id": self.outro_sindicato.id,
                "date_start": date(2026, 1, 1),
                "date_end": date(2026, 12, 31),
                "assistencial_amount": 99.0,
            }
        )
        outro = self._create_contract(self._create_employee("Outro"))
        self.contrato.l10n_br_cct_id = self.cct1
        outro.l10n_br_cct_id = outra_cct
        self.assertAlmostEqualMoney(
            self._get_line_total(self._holerite(self.contrato, 3), "TESTE_CCT"), 35.0
        )
        self.assertAlmostEqualMoney(
            self._get_line_total(self._holerite(outro, 3), "TESTE_CCT"), 99.0
        )

    def test_valor_zero_da_cct_vale(self):
        self.cct1.assistencial_amount = 0.0
        self.contrato.l10n_br_cct_id = self.cct1
        slip = self._holerite(self.contrato, 3)
        self.assertAlmostEqualMoney(self._get_line_total(slip, "TESTE_CCT"), 0.0)

    def test_valores_para_as_regras(self):
        self.assertEqual(self.cct1.assistencial_fator_sindicalizado(), 0.5)
        self.assertEqual(self.cct2.assistencial_fator_sindicalizado(), 0.0)
        job = self.env["hr.job"].create({"name": "Cargo CCT"})
        self.assertEqual(self.cct1.wage_floor_for(job), 0.0)
        self.cct1.wage_floor = 2000.0
        self.assertEqual(self.cct1.wage_floor_for(job), 2000.0)
        self.env["l10n.br.hr.convention.wage.floor"].create(
            {"convention_id": self.cct1.id, "job_id": job.id, "wage_floor": 2500.0}
        )
        self.assertEqual(self.cct1.wage_floor_for(job), 2500.0)
        self.env["l10n.br.hr.convention.vavr.range"].create(
            [
                {"convention_id": self.cct1.id, "wage_ceiling": 3000, "rate_pct": 1},
                {"convention_id": self.cct1.id, "wage_ceiling": 999999, "rate_pct": 20},
            ]
        )
        self.assertAlmostEqual(self.cct1.vavr_rate(3000), 0.01)
        self.assertAlmostEqual(self.cct1.vavr_rate(3000.01), 0.20)
        self.assertIsNone(self.cct2.vavr_rate(1000))

    def test_contribuicao_sindical_do_mes(self):
        self.contrato.l10n_br_cct_id = self.cct1
        self.env["l10n.br.hr.syndicate.contribution"].create(
            [
                {
                    "partner_union_id": self.sindicato.id,
                    "year": 2026,
                    "month": "3",
                    "contribution_type": "sindical",
                    "calc_method": "one_day",
                },
                {
                    "partner_union_id": self.sindicato.id,
                    "year": 2026,
                    "month": "3",
                    "contribution_type": "assistencial",
                    "calc_method": "percent",
                    "percentage": 2.0,
                },
            ]
        )
        slip = self._holerite(self.contrato, 3)
        tools = slip._get_tools_dict()["br"]
        self.assertAlmostEqual(
            tools.contribuicao_sindical(self.contrato, "sindical"), 5000 / 30, places=2
        )
        self.assertAlmostEqual(
            tools.contribuicao_sindical(self.contrato, "assistencial"), 100.0
        )
        self.assertEqual(
            tools.contribuicao_sindical(self.contrato, "confederativa"), 0.0
        )
        abril = self._holerite(self.contrato, 4, calcular=False)
        self.assertEqual(
            abril._get_tools_dict()["br"].contribuicao_sindical(
                self.contrato, "sindical"
            ),
            0.0,
        )

    # --- integridade entre holerites ---------------------------------------
    def test_estrutura_que_le_a_cct(self):
        slip = self._holerite(self.contrato, 3, calcular=False)
        self.assertTrue(slip._l10n_br_le_cct())
        slip.struct_id = self.structure_estatuto
        self.assertFalse(slip._l10n_br_le_cct())

    def test_mudar_valor_da_cct_recalcula_holerite_aberto(self):
        self.contrato.l10n_br_cct_id = self.cct1
        slip = self._holerite(self.contrato, 3)
        self.cct1.assistencial_amount = 40.0
        self.assertAlmostEqualMoney(self._get_line_total(slip, "TESTE_CCT"), 40.0)

    def test_confirmado_de_competencia_fechada_guarda_o_que_valeu(self):
        self.contrato.l10n_br_cct_id = self.cct1
        fechado = self._holerite(self.contrato, 3)
        fechado.action_payslip_done()
        aberto = self._holerite(self.contrato, 4)
        self.cct1.assistencial_amount = 40.0
        self.assertAlmostEqualMoney(self._get_line_total(fechado, "TESTE_CCT"), 35.0)
        self.assertAlmostEqualMoney(self._get_line_total(aberto, "TESTE_CCT"), 40.0)
        self.assertEqual(fechado.state, "done")

    def test_fluxo_de_cadastro_com_folha_fechada(self):
        """Ligar CCT, piso, faixa, contribuição e CCT nova com a folha fechada."""
        slip = self._holerite(self.contrato, 3)
        slip.action_payslip_done()
        self.contrato.l10n_br_cct_id = self.cct1
        self.cct1.wage_floor = 2000.0
        job = self.env["hr.job"].create({"name": "Cargo"})
        self.env["l10n.br.hr.convention.wage.floor"].create(
            {"convention_id": self.cct1.id, "job_id": job.id, "wage_floor": 2500.0}
        )
        self.env["l10n.br.hr.convention.vavr.range"].create(
            {"convention_id": self.cct1.id, "wage_ceiling": 10, "rate_pct": 1}
        )
        self.env["l10n.br.hr.syndicate.contribution"].create(
            {
                "partner_union_id": self.sindicato.id,
                "year": 2026,
                "month": "3",
                "contribution_type": "sindical",
                "calc_method": "one_day",
            }
        )
        self.cct1.date_end = date(2026, 3, 31)
        self.env["l10n.br.hr.collective.convention"].create(
            {
                "name": "CCT retroativa",
                "partner_union_id": self.sindicato.id,
                "date_start": date(2026, 4, 1),
                "date_end": date(2026, 5, 31),
            }
        )
        self.assertEqual(slip.state, "done")

    def test_confirmado_com_aberto_no_mesmo_mes_recusa(self):
        self.contrato.l10n_br_cct_id = self.cct1
        confirmado = self._holerite(self.contrato, 3, dias=(1, 15))
        confirmado.action_payslip_done()
        self._holerite(self.contrato, 3, dias=(16, 31))
        with self.assertRaises(UserError):
            self.cct1.assistencial_amount = 40.0
        self.assertEqual(self.cct1.assistencial_amount, 35.0)
        # Campo que não entra no cálculo segue livre.
        self.cct1.notes = "ok"

    def test_trocar_a_cct_do_contrato_recalcula_aberto_e_poupa_fechado(self):
        self.contrato.l10n_br_cct_id = self.cct1
        fechado = self._holerite(self.contrato, 2)
        fechado.action_payslip_done()
        aberto = self._holerite(self.contrato, 3)
        outra = self.env["l10n.br.hr.collective.convention"].create(
            {
                "name": "CCT B",
                "partner_union_id": self.outro_sindicato.id,
                "date_start": date(2026, 1, 1),
                "date_end": date(2026, 12, 31),
                "assistencial_amount": 99.0,
            }
        )
        self.contrato.write(
            {"l10n_br_cct_id": outra.id, "partner_union": self.outro_sindicato.id}
        )
        self.assertAlmostEqualMoney(self._get_line_total(aberto, "TESTE_CCT"), 99.0)
        self.assertAlmostEqualMoney(self._get_line_total(fechado, "TESTE_CCT"), 35.0)

    def test_apagar_cct_apontada_pelo_contrato_recusa(self):
        self.contrato.l10n_br_cct_id = self.cct1
        with self.assertRaises(UserError):
            self.cct1.unlink()
        self.cct2.unlink()

    # --- lacuna de vigência ------------------------------------------------
    def test_sem_cct_cobrindo_usa_a_ultima_vencida_com_aviso(self):
        self.contrato.l10n_br_cct_id = self.cct1
        slip = self._holerite(self.contrato, 1, ano=2027)
        self.assertAlmostEqualMoney(self._get_line_total(slip, "TESTE_CCT"), 45.0)
        self.assertIn("CCT 2", slip.l10n_br_cct_aviso)
        self.assertIn("2026-12-31", slip.l10n_br_cct_aviso)
        normal = self._holerite(self.contrato, 7)
        self.assertFalse(normal.l10n_br_cct_aviso)

    def test_cct_nova_na_lacuna_recalcula_o_aberto_e_limpa_o_aviso(self):
        self.contrato.l10n_br_cct_id = self.cct1
        slip = self._holerite(self.contrato, 1, ano=2027)
        self.env["l10n.br.hr.collective.convention"].create(
            {
                "name": "CCT 2027",
                "partner_union_id": self.sindicato.id,
                "date_start": date(2027, 1, 1),
                "date_end": date(2027, 12, 31),
                "assistencial_amount": 60.0,
            }
        )
        self.assertAlmostEqualMoney(self._get_line_total(slip, "TESTE_CCT"), 60.0)
        self.assertFalse(slip.l10n_br_cct_aviso)

    def test_antes_da_primeira_cct_segue_sem_cct(self):
        self.contrato.l10n_br_cct_id = self.cct1
        self.assertFalse(self.contrato._l10n_br_cct_vigente(date(2025, 12, 31)))

    # --- faixas de VA/VR ---------------------------------------------------
    def test_faixas_com_o_mesmo_teto_sao_recusadas(self):
        Faixa = self.env["l10n.br.hr.convention.vavr.range"]
        Faixa.create(
            {"convention_id": self.cct1.id, "wage_ceiling": 3000, "rate_pct": 1}
        )
        with self.assertRaises(ValidationError):
            Faixa.create(
                {"convention_id": self.cct1.id, "wage_ceiling": 3000, "rate_pct": 5}
            )

    def test_salario_acima_da_ultima_faixa_e_erro_claro(self):
        self.env["l10n.br.hr.convention.vavr.range"].create(
            {"convention_id": self.cct1.id, "wage_ceiling": 3000, "rate_pct": 1}
        )
        with self.assertRaises(UserError):
            self.cct1.vavr_rate(3000.01)
