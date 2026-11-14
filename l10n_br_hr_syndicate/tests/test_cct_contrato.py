# Copyright 2024 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""CCT ligada ao contrato e lida pelas regras na competência do holerite (TG-109)."""
from datetime import date

from dateutil.relativedelta import relativedelta
from freezegun import freeze_time

from odoo import fields
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
        # Competência corrente: o corte da integridade é pela data de hoje.
        cls.hoje = fields.Date.context_today(cls.env["hr.payslip"])
        cls.sind_hoje = Partner.create(
            {"name": "Sindicato Hoje", "union_entity_code": "SH1", "is_company": True}
        )
        cls.cct_hoje = Cct.create(
            {
                "name": "CCT Hoje",
                "partner_union_id": cls.sind_hoje.id,
                "date_start": date(cls.hoje.year - 1, 1, 1),
                "date_end": date(cls.hoje.year + 1, 12, 31),
                "assistencial_amount": 35.0,
            }
        )

    def setUp(self):
        super().setUp()
        self.empregado = self._create_employee("Empregado CCT")
        self.contrato = self._create_contract(self.empregado)

    def _holerite_hoje(self, contrato, meses=0, calcular=True):
        """Holerite do mês corrente (``meses`` = 0) ou de outro, a partir de hoje."""
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

    def _contrato_hoje(self):
        contrato = self._create_contract(self._create_employee("Empregado Hoje"))
        contrato.l10n_br_cct_id = self.cct_hoje
        return contrato

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
        slip = self._holerite_hoje(self._contrato_hoje())
        self.cct_hoje.assistencial_amount = 40.0
        self.assertAlmostEqualMoney(self._get_line_total(slip, "TESTE_CCT"), 40.0)

    def test_recalculo_so_do_rascunho_ja_calculado_da_competencia_corrente(self):
        contrato = self._contrato_hoje()
        antigo = self._holerite_hoje(contrato, meses=-3)
        nunca = self._holerite_hoje(contrato, meses=1, calcular=False)
        corrente = self._holerite_hoje(contrato)
        self.cct_hoje.assistencial_amount = 40.0
        self.assertAlmostEqualMoney(self._get_line_total(corrente, "TESTE_CCT"), 40.0)
        self.assertAlmostEqualMoney(self._get_line_total(antigo, "TESTE_CCT"), 35.0)
        self.assertFalse(nunca.line_ids)

    def test_confirmado_de_competencia_anterior_guarda_o_que_valeu(self):
        contrato = self._contrato_hoje()
        fechado = self._holerite_hoje(contrato, meses=-2)
        fechado.action_payslip_done()
        aberto = self._holerite_hoje(contrato)
        self.cct_hoje.assistencial_amount = 40.0
        self.assertAlmostEqualMoney(self._get_line_total(fechado, "TESTE_CCT"), 35.0)
        self.assertAlmostEqualMoney(self._get_line_total(aberto, "TESTE_CCT"), 40.0)
        self.assertEqual(fechado.state, "done")

    def test_confirmado_da_competencia_corrente_recusa(self):
        contrato = self._contrato_hoje()
        slip = self._holerite_hoje(contrato)
        slip.action_payslip_done()
        with self.assertRaises(UserError):
            self.cct_hoje.assistencial_amount = 45.0
        with self.assertRaises(UserError):
            contrato.l10n_br_cct_id = False
        self.assertEqual(self.cct_hoje.assistencial_amount, 35.0)
        # Campo que não entra no cálculo segue livre.
        self.cct_hoje.notes = "ok"

    def test_confirmado_de_competencia_futura_recusa(self):
        slip = self._holerite_hoje(self._contrato_hoje(), meses=1)
        slip.action_payslip_done()
        with self.assertRaises(UserError):
            self.cct_hoje.assistencial_amount = 45.0

    def test_rascunho_irmao_de_outra_estrutura_nao_trava_competencia_fechada(self):
        contrato = self._contrato_hoje()
        fechado = self._holerite_hoje(contrato, meses=-2)
        fechado.action_payslip_done()
        irmao = self._holerite_hoje(contrato, meses=-2, calcular=False)
        irmao.write({"struct_id": self.structure_estatuto.id})
        self.cct_hoje.wage_floor = 2000.0
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

    def test_trocar_a_cct_do_contrato_recalcula_aberto_e_poupa_fechado(self):
        contrato = self._contrato_hoje()
        fechado = self._holerite_hoje(contrato, meses=-2)
        fechado.action_payslip_done()
        aberto = self._holerite_hoje(contrato)
        outra = self.env["l10n.br.hr.collective.convention"].create(
            {
                "name": "CCT B Hoje",
                "partner_union_id": self.outro_sindicato.id,
                "date_start": date(self.hoje.year - 1, 1, 1),
                "date_end": date(self.hoje.year + 1, 12, 31),
                "assistencial_amount": 99.0,
            }
        )
        contrato.write(
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
        """A lacuna é relativa a hoje: a CCT termina no mês anterior ao corrente."""
        inicio_mes = self.hoje.replace(day=1)
        Cct = self.env["l10n.br.hr.collective.convention"]
        # Sem as CCT de 2026 do setUpClass no caminho do mesmo sindicato.
        (self.cct1 | self.cct2).write({"active": False})
        velha = Cct.create(
            {
                "name": "CCT Lacuna Velha",
                "partner_union_id": self.sindicato.id,
                "date_start": date(self.hoje.year - 3, 1, 1),
                "date_end": inicio_mes - relativedelta(days=1),
                "assistencial_amount": 45.0,
            }
        )
        self.contrato.l10n_br_cct_id = velha
        slip = self._holerite_hoje(self.contrato)
        self.assertAlmostEqualMoney(self._get_line_total(slip, "TESTE_CCT"), 45.0)
        self.assertIn("CCT Lacuna Velha", slip.l10n_br_cct_aviso)
        Cct.create(
            {
                "name": "CCT Lacuna Nova",
                "partner_union_id": self.sindicato.id,
                "date_start": inicio_mes,
                "date_end": inicio_mes + relativedelta(years=1, days=-1),
                "assistencial_amount": 60.0,
            }
        )
        self.assertAlmostEqualMoney(self._get_line_total(slip, "TESTE_CCT"), 60.0)
        self.assertFalse(slip.l10n_br_cct_aviso)

    def _faixa(self, cct, teto, taxa):
        return self.env["l10n.br.hr.convention.vavr.range"].create(
            {"convention_id": cct.id, "wage_ceiling": teto, "rate_pct": taxa}
        )

    def test_faixas_com_o_mesmo_teto_sao_recusadas(self):
        self._faixa(self.cct1, 3000, 1)
        with self.assertRaises(ValidationError):
            self._faixa(self.cct1, 3000, 5)

    def test_duas_faixas_abertas_sao_recusadas(self):
        self._faixa(self.cct1, 0, 20)
        with self.assertRaises(ValidationError):
            self._faixa(self.cct1, 0, 30)

    def test_teto_negativo_e_percentual_fora_de_0_a_100_sao_recusados(self):
        with self.assertRaises(ValidationError):
            self._faixa(self.cct1, -1, 5)
        with self.assertRaises(ValidationError):
            self._faixa(self.cct1, 100, 150)
        with self.assertRaises(ValidationError):
            self._faixa(self.cct1, 100, -1)

    def test_faixa_aberta_acima_de(self):
        self._faixa(self.cct1, 3000, 1)
        self._faixa(self.cct1, 0, 20)
        self.assertAlmostEqual(self.cct1.vavr_rate(3000), 0.01)
        self.assertAlmostEqual(self.cct1.vavr_rate(3000.01), 0.20)
        self.assertAlmostEqual(self.cct1.vavr_rate(1000000), 0.20)

    def test_salario_sem_faixa_que_cubra_e_erro_claro(self):
        self._faixa(self.cct1, 3000, 1)
        with self.assertRaises(UserError):
            self.cct1.vavr_rate(3000.01)

    # --- CCT arquivada e antes da primeira ---------------------------------
    def test_arquivar_a_unica_cct_do_sindicato_da_aviso(self):
        contrato = self._contrato_hoje()
        self.cct_hoje.active = False
        slip = self._holerite_hoje(contrato)
        self.assertAlmostEqualMoney(self._get_line_total(slip, "TESTE_CCT"), 35.0)
        self.assertIn("CCT Hoje", slip.l10n_br_cct_aviso)
        self.assertIn("arquivada", slip.l10n_br_cct_aviso)

    def test_antes_da_primeira_cct_usa_a_primeira_com_aviso(self):
        self.contrato.l10n_br_cct_id = self.cct1
        slip = self._holerite(self.contrato, 12, ano=2025)
        self.assertAlmostEqualMoney(self._get_line_total(slip, "TESTE_CCT"), 35.0)
        self.assertIn("anterior à primeira", slip.l10n_br_cct_aviso)


# A integridade e o recálculo dependem de "hoje": a mesma classe roda congelada
# em datas de virada (mês, ano, ano bissexto), para nenhum caso envelhecer.
DATAS_CONGELADAS = (
    "2026-11-01",
    "2026-12-31",
    "2027-02-01",
    "2028-02-29",
    "2029-01-01",
)


def _variante_congelada(data):
    class _Congelada(TestCctContrato):
        _data_congelada = data
        # O carregador do Odoo só roda métodos de teste do próprio ``__dict__``.
        allow_inherited_tests_method = True

        @classmethod
        def setUpClass(cls):
            cls._congelador = freeze_time(cls._data_congelada)
            cls._congelador.start()
            try:
                super().setUpClass()
            except BaseException:
                cls._congelador.stop()
                raise

        @classmethod
        def tearDownClass(cls):
            try:
                super().tearDownClass()
            finally:
                cls._congelador.stop()

    _Congelada.__name__ = _Congelada.__qualname__ = "TestCctContrato" + data.replace(
        "-", ""
    )
    return _Congelada


for _data in DATAS_CONGELADAS:
    _classe = _variante_congelada(_data)
    globals()[_classe.__name__] = _classe
del _data, _classe
