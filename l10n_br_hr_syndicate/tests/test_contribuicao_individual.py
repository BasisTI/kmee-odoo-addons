# Copyright 2024 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""Oposição e sindicalista individuais nas contribuições 617 e 602 (TG-142)."""
from datetime import date

from dateutil.relativedelta import relativedelta

from odoo import fields
from odoo.exceptions import UserError, ValidationError

from odoo.addons.l10n_br_hr_payroll.tests.common import PayrollCommon


class TestContribuicaoIndividual(PayrollCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Partner = cls.env["res.partner"]
        cls.sindicato = Partner.create(
            {"name": "Sindicato I", "union_entity_code": "SI1", "is_company": True}
        )
        cls.hoje = fields.Date.context_today(cls.env["hr.payslip"])
        Cct = cls.env["l10n.br.hr.collective.convention"]
        cls.cct = Cct.create(
            {
                "name": "CCT I",
                "partner_union_id": cls.sindicato.id,
                "date_start": date(cls.hoje.year - 1, 1, 1),
                "date_end": date(cls.hoje.year + 1, 12, 31),
                "assistencial_sindicalizado": "half",
                "assistencial_exempt_trial": True,
            }
        )
        Tipo = cls.env["hr.contract.type"]
        cls.tipo_clt = Tipo.create({"name": "CLT Teste"})
        cls.tipo_aprendiz = Tipo.create({"name": "Aprendiz Teste"})
        cls.tipo_prazo = Tipo.create(
            {"name": "Contrato a Termo", "l10n_br_prazo_determinado": True}
        )
        cls.cct.assistencial_exempt_contract_type_ids = cls.tipo_aprendiz
        Contrib = cls.env["l10n.br.hr.syndicate.contribution"]
        for ano, mes in ((2026, "3"), (cls.hoje.year, str(cls.hoje.month))):
            Contrib.create(
                [
                    {
                        "partner_union_id": cls.sindicato.id,
                        "year": ano,
                        "month": mes,
                        "contribution_type": "assistencial",
                        "calc_method": "fixed",
                        "fixed_amount": 40.0,
                    },
                    {
                        "partner_union_id": cls.sindicato.id,
                        "year": ano,
                        "month": mes,
                        "contribution_type": "sindical",
                        "calc_method": "fixed",
                        "fixed_amount": 20.0,
                    },
                ]
            )
        cls.regra = cls.env["hr.salary.rule"].create(
            {
                "name": "Teste 617",
                "code": "TESTE_617",
                "sequence": 221,
                "category_id": cls.env.ref(
                    "l10n_br_hr_payroll.hr_salary_rule_category_info"
                ).id,
                "condition_select": "none",
                "amount_select": "code",
                "amount_python_compute": (
                    "result = tools.br.contribuicao_sindical("
                    "contract, 'assistencial')"
                ),
            }
        )
        cls.structure_clt.write({"rule_ids": [(4, cls.regra.id)]})

    def setUp(self):
        super().setUp()
        self.empregado = self._create_employee("Empregado Individual")
        self.contrato = self._create_contract(self.empregado)
        self.contrato.l10n_br_cct_id = self.cct
        self.contrato.contract_type_id = self.tipo_clt
        self.mar = date(2026, 3, 31)

    def _mes(self, contrato, meses=0, calcular=True):
        mes = self.hoje.replace(day=1) + relativedelta(months=meses)
        slip = self.env["hr.payslip"].create(
            {
                "name": f"Holerite {mes}",
                "employee_id": contrato.employee_id.id,
                "contract_id": contrato.id,
                "struct_id": contrato.struct_id.id,
                "date_from": mes,
                "date_to": mes.replace(day=28),
                "company_id": self.env.company.id,
            }
        )
        if calcular:
            slip.compute_sheet()
        return slip

    def _r(self, tipo, data=None, contrato=None):
        return (contrato or self.contrato)._l10n_br_contribuicao_resolver(
            data or self.mar, tipo
        )

    # --- 617 ---------------------------------------------------------------
    def test_617_sem_marca_paga_o_valor_da_cct(self):
        self.assertEqual(self._r("assistencial"), (40.0, False))

    def test_617_opositor_paga_zero_e_nao_fica_em_branco(self):
        self.empregado.l10n_br_oposicao_contribuicao = True
        self.assertEqual(self._r("assistencial"), (0.0, "oposicao"))

    def test_617_oposicao_prevalece_sobre_sindicalista(self):
        self.empregado.write(
            {"l10n_br_oposicao_contribuicao": True, "l10n_br_sindicalista": True}
        )
        self.assertEqual(self._r("assistencial"), (0.0, "oposicao"))

    def test_617_sindicalista_integral_metade_ou_nada(self):
        self.empregado.l10n_br_sindicalista = True
        self.assertEqual(self._r("assistencial"), (20.0, "sindicalizado_metade"))
        self.cct.assistencial_sindicalizado = "full"
        self.assertEqual(self._r("assistencial"), (40.0, False))
        self.cct.assistencial_sindicalizado = "zero"
        self.assertEqual(self._r("assistencial"), (0.0, "sindicalizado_isento"))

    def test_617_tipo_de_contratacao_isento_na_cct(self):
        self.contrato.contract_type_id = self.tipo_aprendiz
        self.assertEqual(self._r("assistencial"), (0.0, "tipo_contratacao"))

    def test_617_isencao_vem_antes_da_marca_de_sindicalista(self):
        self.empregado.l10n_br_sindicalista = True
        self.contrato.contract_type_id = self.tipo_aprendiz
        self.assertEqual(self._r("assistencial"), (0.0, "tipo_contratacao"))

    def test_617_experiencia_isenta_ate_o_fim_do_mes(self):
        self.contrato.trial_date_end = date(2026, 3, 31)
        self.assertEqual(self._r("assistencial"), (0.0, "experiencia"))

    def test_617_experiencia_que_termina_no_meio_do_mes_ja_deve_o_mes(self):
        self.contrato.trial_date_end = date(2026, 3, 15)
        self.assertEqual(self._r("assistencial"), (40.0, False))

    def test_617_cct_sem_isencao_de_experiencia_cobra(self):
        self.cct.assistencial_exempt_trial = False
        self.contrato.trial_date_end = date(2026, 3, 31)
        self.assertEqual(self._r("assistencial"), (40.0, False))

    def test_617_metade_arredonda_para_cima_como_o_java(self):
        self.env["l10n.br.hr.syndicate.contribution"].search(
            [("month", "=", "3"), ("contribution_type", "=", "assistencial")]
        ).fixed_amount = 35.05
        self.empregado.l10n_br_sindicalista = True
        self.assertEqual(self._r("assistencial"), (17.53, "sindicalizado_metade"))

    def test_617_prazo_determinado_nao_e_experiencia(self):
        self.contrato.write(
            {"contract_type_id": self.tipo_prazo.id, "trial_date_end": self.mar}
        )
        self.assertEqual(self._r("assistencial"), (40.0, False))

    def test_617_sem_regra_na_competencia_fica_em_branco(self):
        # Abril não tem contribuição cadastrada: lacuna, não isenção.
        self.assertEqual(self._r("assistencial", date(2026, 4, 30)), (None, False))
        self.empregado.l10n_br_oposicao_contribuicao = True
        self.assertEqual(self._r("assistencial", date(2026, 4, 30)), (None, False))
        slip = self._mes(self.contrato, calcular=False)
        tools = slip._get_tools_dict()["br"]
        self.assertEqual(
            tools.contribuicao_sindical(self.contrato, "confederativa"), 0.0
        )

    def test_617_contrato_sem_cct_fica_em_branco(self):
        contrato = self._create_contract(self._create_employee("Sem CCT"))
        self.assertEqual(self._r("assistencial", contrato=contrato), (None, False))

    # --- 602 ---------------------------------------------------------------
    def test_602_so_sindicalista_paga_o_valor_da_cct(self):
        self.assertEqual(self._r("sindical"), (None, False))
        self.empregado.l10n_br_sindicalista = True
        self.assertEqual(self._r("sindical"), (20.0, False))

    def test_602_opositor_sindicalista_continua_pagando_o_602(self):
        self.empregado.write(
            {"l10n_br_oposicao_contribuicao": True, "l10n_br_sindicalista": True}
        )
        self.assertEqual(self._r("sindical"), (20.0, False))

    def test_602_valor_individual_prevalece_e_vale_sem_a_marca(self):
        Individual = self.env["l10n.br.hr.syndicate.individual.value"]
        Individual.create(
            {
                "employee_id": self.empregado.id,
                "date_start": date(2026, 1, 1),
                "date_end": date(2026, 3, 31),
                "amount": 55.0,
            }
        )
        self.assertEqual(self._r("sindical"), (55.0, "valor_individual"))
        self.empregado.l10n_br_sindicalista = True
        self.assertEqual(self._r("sindical"), (55.0, "valor_individual"))

    def test_602_vigencia_vale_se_cobre_o_dia_1_da_competencia(self):
        Individual = self.env["l10n.br.hr.syndicate.individual.value"]
        Individual.create(
            {
                "employee_id": self.empregado.id,
                "date_start": date(2026, 3, 15),
                "amount": 22.0,
            }
        )
        # Começa no dia 15: não cobre o dia 1 de março (como o Sistema DP).
        self.assertEqual(self._r("sindical"), (None, False))
        self.assertEqual(
            self._r("sindical", date(2026, 4, 30)), (22.0, "valor_individual")
        )

    def test_602_duas_vigencias_no_mes_vale_a_que_cobre_o_dia_1(self):
        Individual = self.env["l10n.br.hr.syndicate.individual.value"]
        Individual.create(
            [
                {
                    "employee_id": self.empregado.id,
                    "date_start": date(2026, 1, 1),
                    "date_end": date(2026, 3, 15),
                    "amount": 10.0,
                },
                {
                    "employee_id": self.empregado.id,
                    "date_start": date(2026, 3, 16),
                    "amount": 22.0,
                },
            ]
        )
        self.assertEqual(self._r("sindical"), (10.0, "valor_individual"))

    def test_602_valor_individual_fora_da_vigencia_volta_a_regra_da_cct(self):
        self.env["l10n.br.hr.syndicate.individual.value"].create(
            {
                "employee_id": self.empregado.id,
                "date_start": date(2026, 1, 1),
                "date_end": date(2026, 2, 28),
                "amount": 55.0,
            }
        )
        self.assertEqual(self._r("sindical"), (None, False))
        self.empregado.l10n_br_sindicalista = True
        self.assertEqual(self._r("sindical"), (20.0, False))

    def test_602_valor_individual_vale_sem_regra_da_cct_no_mes(self):
        self.env["l10n.br.hr.syndicate.individual.value"].create(
            {
                "employee_id": self.empregado.id,
                "date_start": date(2026, 1, 1),
                "amount": 55.0,
            }
        )
        self.assertEqual(
            self._r("sindical", date(2026, 4, 30)), (55.0, "valor_individual")
        )

    def test_602_vigencias_individuais_nao_se_sobrepoem(self):
        Individual = self.env["l10n.br.hr.syndicate.individual.value"]
        Individual.create(
            {
                "employee_id": self.empregado.id,
                "date_start": date(2026, 1, 1),
                "date_end": date(2026, 6, 30),
                "amount": 55.0,
            }
        )
        with self.assertRaises(ValidationError):
            Individual.create(
                {
                    "employee_id": self.empregado.id,
                    "date_start": date(2026, 6, 1),
                    "amount": 60.0,
                }
            )
        with self.assertRaises(ValidationError):
            Individual.create(
                {
                    "employee_id": self.empregado.id,
                    "date_start": date(2026, 9, 1),
                    "date_end": date(2026, 8, 1),
                    "amount": 60.0,
                }
            )

    def test_ferramenta_devolve_float_e_detalhe(self):
        slip = self._mes(self.contrato, calcular=False)
        tools = slip._get_tools_dict()["br"]
        self.assertEqual(
            tools.contribuicao_sindical_detalhe(self.contrato, "assistencial"),
            (40.0, False),
        )
        self.assertEqual(tools.contribuicao_sindical(self.contrato, "sindical"), 0.0)
        self.assertIsNone(
            tools.contribuicao_sindical_detalhe(self.contrato, "sindical")[0]
        )

    # --- integridade entre holerites ----------------------------------------
    def test_marcar_oposicao_recalcula_o_holerite_aberto(self):
        aberto = self._mes(self.contrato)
        self.assertAlmostEqualMoney(self._get_line_total(aberto, "TESTE_617"), 40.0)
        self.empregado.l10n_br_oposicao_contribuicao = True
        self.assertAlmostEqualMoney(self._get_line_total(aberto, "TESTE_617"), 0.0)
        self.empregado.write(
            {"l10n_br_oposicao_contribuicao": False, "l10n_br_sindicalista": True}
        )
        self.assertAlmostEqualMoney(self._get_line_total(aberto, "TESTE_617"), 20.0)

    def test_holerite_confirmado_da_competencia_corrente_recusa_a_mudanca(self):
        slip = self._mes(self.contrato)
        slip.action_payslip_done()
        with self.assertRaises(UserError):
            self.empregado.l10n_br_oposicao_contribuicao = True

    def test_holerite_de_competencia_anterior_guarda_o_que_valeu(self):
        passado = self._mes(self.contrato, meses=-3)
        passado.action_payslip_done()
        valor = self._get_line_total(passado, "TESTE_617")
        self.empregado.l10n_br_oposicao_contribuicao = True
        self.assertAlmostEqualMoney(self._get_line_total(passado, "TESTE_617"), valor)

    def test_mudar_tipo_de_contratacao_ou_experiencia_recalcula_o_aberto(self):
        aberto = self._mes(self.contrato)
        self.contrato.contract_type_id = self.tipo_aprendiz
        self.assertAlmostEqualMoney(self._get_line_total(aberto, "TESTE_617"), 0.0)
        self.contrato.contract_type_id = self.tipo_clt
        self.assertAlmostEqualMoney(self._get_line_total(aberto, "TESTE_617"), 40.0)
        self.contrato.trial_date_end = self.hoje.replace(day=1) + relativedelta(
            months=1, days=-1
        )
        self.assertAlmostEqualMoney(self._get_line_total(aberto, "TESTE_617"), 0.0)

    def test_prazo_determinado_e_booleano_e_renomear_nao_muda_nada(self):
        self.tipo_prazo.name = "Prazo Determinado"
        self.tipo_clt.name = "Contrato por Prazo Determinado"
        self.contrato.write({"trial_date_end": self.mar})
        self.assertEqual(self._r("assistencial"), (0.0, "experiencia"))
        self.contrato.contract_type_id = self.tipo_prazo
        self.assertEqual(self._r("assistencial"), (40.0, False))

    def test_marcar_prazo_determinado_recalcula_aberto_e_recusa_confirmado(self):
        self.contrato.trial_date_end = self.hoje.replace(day=1) + relativedelta(
            months=1, days=-1
        )
        aberto = self._mes(self.contrato)
        self.assertAlmostEqualMoney(self._get_line_total(aberto, "TESTE_617"), 0.0)
        self.tipo_clt.l10n_br_prazo_determinado = True
        self.assertAlmostEqualMoney(self._get_line_total(aberto, "TESTE_617"), 40.0)
        aberto.action_payslip_done()
        with self.assertRaises(UserError):
            self.tipo_clt.l10n_br_prazo_determinado = False

    def test_mudanca_sem_efeito_nao_recusa_confirmado(self):
        slip = self._mes(self.contrato)
        slip.action_payslip_done()
        # Vigência antiga que não cobre a competência corrente.
        self.env["l10n.br.hr.syndicate.individual.value"].create(
            {
                "employee_id": self.empregado.id,
                "date_start": date(2026, 1, 1),
                "date_end": date(2026, 3, 31),
                "amount": 22.0,
            }
        )
        # Fim da experiência anterior à competência.
        self.contrato.trial_date_end = date(2025, 1, 31)
        self.assertEqual(slip.state, "done")
        self.assertAlmostEqualMoney(self._get_line_total(slip, "TESTE_617"), 40.0)

    def test_tipos_isentos_da_cct_mudam_o_calculo_do_aberto(self):
        aberto = self._mes(self.contrato)
        self.cct.assistencial_exempt_contract_type_ids = self.tipo_clt
        self.assertAlmostEqualMoney(self._get_line_total(aberto, "TESTE_617"), 0.0)

    def test_valor_individual_recalcula_o_aberto_e_recusa_o_confirmado(self):
        Individual = self.env["l10n.br.hr.syndicate.individual.value"]
        regra = self.regra.copy(
            {
                "code": "TESTE_602",
                "name": "Teste 602",
                "sequence": 222,
                "amount_python_compute": (
                    "result = tools.br.contribuicao_sindical(contract, 'sindical')"
                ),
            }
        )
        self.structure_clt.write({"rule_ids": [(4, regra.id)]})
        aberto = self._mes(self.contrato)
        self.assertAlmostEqualMoney(self._get_line_total(aberto, "TESTE_602"), 0.0)
        valor = Individual.create(
            {
                "employee_id": self.empregado.id,
                "date_start": self.hoje.replace(day=1),
                "amount": 77.0,
            }
        )
        self.assertAlmostEqualMoney(self._get_line_total(aberto, "TESTE_602"), 77.0)
        aberto.action_payslip_done()
        with self.assertRaises(UserError):
            valor.amount = 10.0
        with self.assertRaises(UserError):
            valor.unlink()
