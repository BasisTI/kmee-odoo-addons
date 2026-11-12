# Copyright 2026 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

"""S-1210 (TG-106): ``infoIRComplem`` com as deduções do informe de rendimentos.

Conferido com o evtPgtos do leiaute S-1.3 (pacote XSD 2026-10-26, NT 07/2026
rev. 20/10/2026): grupos ``infoDep``, ``infoIRCR`` (``dedDepen``, ``penAlim``,
``previdCompl``) e ``planSaude``, na ordem e com os nomes do XSD.
"""

from lxml import etree

from odoo.exceptions import UserError
from odoo.tests import tagged

from .common import HAS_ESOCIALLIB, RECIBO_S1200, ESocialCicloCommon

NS = {"e": "http://www.esocial.gov.br/schema/evt/evtPgtos/v_S_01_03_00"}
CPF_FILHA = "52998224725"
CPF_FILHO = "11144477735"
CNPJ_OPERADORA = "11222333000181"
CNPJ_ENTIDADE = "11444777000161"


@tagged("post_install", "-at_install")
class TestS1210InfoIRComplem(ESocialCicloCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.tipo_filho = cls.env["l10n_br.esocial.tipo.dependente"].search(
            [("codigo", "=", "03"), ("dt_fim", "=", False)], limit=1
        )
        cls.relacao = cls.env.ref("hr_employee_relative.relation_child")

    def setUp(self):
        super().setUp()
        self.regras = {}

    # --- apoio -----------------------------------------------------------
    def _regra(self, cod_inc_irrf, tp_rubr="2"):
        chave = (cod_inc_irrf, tp_rubr)
        if chave not in self.regras:
            codigo = "TST_%s_%s" % chave
            self.regras[chave] = self.rule.copy(
                {
                    "name": "Rubrica de teste %s" % cod_inc_irrf,
                    "code": codigo,
                    "l10n_br_esocial_cod_rubr": codigo,
                    "l10n_br_esocial_tp_rubr": tp_rubr,
                    "l10n_br_esocial_cod_inc_irrf": cod_inc_irrf,
                }
            )
        return self.regras[chave]

    def _holerite(self, descontos=(), irrf=False, gerar=True):
        """Holerite pago em 2024-04 com os descontos ``(cod_inc_irrf, valor)``."""
        payslip = self._criar_payslip(data_pagamento="2024-04-05")
        for cod, valor in descontos:
            regra = self._regra(cod)
            self.env["hr.payslip.line"].create(
                {
                    "slip_id": payslip.id,
                    "salary_rule_id": regra.id,
                    "name": regra.name,
                    "code": regra.code,
                    "employee_id": self.employee.id,
                    "contract_id": self.contract.id,
                    "quantity": 1,
                    "amount": valor,
                    "rate": 100,
                }
            )
        if irrf:
            self.env["hr.payslip.line"].create(
                {
                    "slip_id": payslip.id,
                    "salary_rule_id": self.rule.id,
                    "name": "IRRF",
                    "code": "IRRF",
                    "employee_id": self.employee.id,
                    "contract_id": self.contract.id,
                    "quantity": 1,
                    "amount": 85.2,
                    "rate": 100,
                }
            )
        payslip.action_esocial_gerar_s1200()
        s1200 = payslip.l10n_br_esocial_s1200_id
        s1200.evento_id.write({"state": "success", "nr_recibo": RECIBO_S1200})
        if not gerar:
            return payslip
        payslip.action_esocial_gerar_s1210()
        return payslip.l10n_br_esocial_s1210_id

    def _parente(self, **extra):
        vals = {
            "employee_id": self.employee.id,
            "relation_id": self.relacao.id,
            "name": "Filha de Teste",
            "date_of_birth": "2015-03-20",
            "l10n_br_esocial_cpf": CPF_FILHA,
        }
        vals.update(extra)
        return self.env["hr.employee.relative"].create(vals)

    def _dependente_irrf(self, **extra):
        vals = {
            "l10n_br_esocial_tp_dep_id": self.tipo_filho.id,
            "l10n_br_esocial_dep_irrf": True,
        }
        vals.update(extra)
        return self._parente(**vals)

    def _xml(self, s1210):
        xml = s1210.evento_id.xml_envio
        return etree.fromstring(xml.encode("utf-8"))

    # --- sem dedução -------------------------------------------------------
    def test_sem_deducao_nao_tem_info_ir_complem(self):
        s1210 = self._holerite()
        self.assertFalse(s1210._info_ir_complem())

    # --- pensão alimentícia ----------------------------------------------
    def test_pensao_vai_em_pen_alim_e_o_alimentando_em_info_dep(self):
        """O alimentando sem tipo de dependente é declarado em ``infoDep``."""
        self._parente(l10n_br_esocial_pensao_alimenticia=True)
        ir = self._holerite(descontos=[("51", 620.0)])._info_ir_complem()
        self.assertEqual(ir["tp_cr"], "056107")
        self.assertEqual(ir["pen_alim"], {("11", CPF_FILHA): 620.0})
        self.assertEqual(
            ir["info_dep"],
            [
                {
                    "cpf_dep": CPF_FILHA,
                    "dt_nascto": "2015-03-20",
                    "nome": "Filha de Teste",
                }
            ],
        )

    def test_dependente_ja_cadastrado_nao_repete_em_info_dep(self):
        """Quem o S-2200 já cadastrou não entra em ``infoDep`` (leiaute)."""
        self._dependente_irrf(l10n_br_esocial_pensao_alimenticia=True)
        self.employee.l10n_br_irrf_dependentes = 1
        ir = self._holerite(descontos=[("52", 300.0)])._info_ir_complem()
        self.assertEqual(ir["info_dep"], [])
        self.assertEqual(ir["pen_alim"], {("11", CPF_FILHA): 300.0})

    def test_pensao_sem_beneficiario_e_recusada(self):
        payslip = self._holerite(descontos=[("51", 620.0)], gerar=False)
        with self.assertRaisesRegex(UserError, "Beneficiário da Pensão"):
            payslip.action_esocial_gerar_s1210()

    def test_pensao_com_dois_beneficiarios_e_recusada(self):
        self._parente(l10n_br_esocial_pensao_alimenticia=True)
        self._parente(
            name="Filho de Teste",
            l10n_br_esocial_cpf=CPF_FILHO,
            l10n_br_esocial_pensao_alimenticia=True,
        )
        payslip = self._holerite(descontos=[("51", 620.0)], gerar=False)
        with self.assertRaisesRegex(UserError, "2 beneficiários"):
            payslip.action_esocial_gerar_s1210()

    def test_pensao_sem_cpf_do_alimentando_e_recusada(self):
        self._parente(
            l10n_br_esocial_pensao_alimenticia=True, l10n_br_esocial_cpf=False
        )
        payslip = self._holerite(descontos=[("51", 620.0)], gerar=False)
        with self.assertRaisesRegex(UserError, "CPF válido"):
            payslip.action_esocial_gerar_s1210()

    # --- dependentes (dedução do IRRF) -----------------------------------
    def test_deducao_por_dependente(self):
        self._dependente_irrf()
        self._dependente_irrf(name="Filho de Teste", l10n_br_esocial_cpf=CPF_FILHO)
        self.employee.l10n_br_irrf_dependentes = 2
        s1210 = self._holerite(irrf=True)
        valor = self.env["l10n_br.hr.payroll.irrf.dependente"]._valor("2024-03-31")
        ir = s1210._info_ir_complem()
        self.assertEqual(
            ir["ded_dependentes"],
            {("11", CPF_FILHA): valor, ("11", CPF_FILHO): valor},
        )
        self.assertEqual(ir["info_dep"], [])

    def test_dependentes_da_folha_diferentes_do_cadastro_sao_recusados(self):
        self._dependente_irrf()
        self.employee.l10n_br_irrf_dependentes = 3
        payslip = self._holerite(irrf=True, gerar=False)
        with self.assertRaisesRegex(UserError, "deduz 3 dependente"):
            payslip.action_esocial_gerar_s1210()

    # --- plano de saúde --------------------------------------------------
    def test_plano_de_saude_separa_titular_e_dependente(self):
        self.contract.write(
            {
                "l10n_br_esocial_cnpj_oper_saude": "11.222.333/0001-81",
                "l10n_br_esocial_reg_ans": "123456",
            }
        )
        self._dependente_irrf(l10n_br_esocial_vlr_saude=100.0)
        self.employee.l10n_br_irrf_dependentes = 1
        ir = self._holerite(descontos=[("67", 300.0)])._info_ir_complem()
        self.assertEqual(
            ir["plano"],
            {
                "cnpj_oper": CNPJ_OPERADORA,
                "reg_ans": "123456",
                "titular": 200.0,
                "dependentes": {CPF_FILHA: 100.0},
            },
        )

    def test_plano_de_saude_so_dos_dependentes_tem_titular_zero(self):
        self.contract.l10n_br_esocial_cnpj_oper_saude = CNPJ_OPERADORA
        self._parente(l10n_br_esocial_vlr_saude=300.0)
        ir = self._holerite(descontos=[("9067", 300.0)])._info_ir_complem()
        self.assertEqual(ir["plano"]["titular"], 0.0)
        self.assertEqual(ir["plano"]["dependentes"], {CPF_FILHA: 300.0})
        # o dependente do plano sem tipo eSocial também vai em infoDep
        self.assertEqual([d["cpf_dep"] for d in ir["info_dep"]], [CPF_FILHA])

    def test_plano_de_saude_sem_operadora_e_recusado(self):
        payslip = self._holerite(descontos=[("67", 300.0)], gerar=False)
        with self.assertRaisesRegex(UserError, "Operadora do Plano"):
            payslip.action_esocial_gerar_s1210()

    def test_plano_dos_dependentes_acima_do_desconto_e_recusado(self):
        self.contract.l10n_br_esocial_cnpj_oper_saude = CNPJ_OPERADORA
        self._parente(l10n_br_esocial_vlr_saude=400.0)
        payslip = self._holerite(descontos=[("67", 300.0)], gerar=False)
        with self.assertRaisesRegex(UserError, "passam do desconto"):
            payslip.action_esocial_gerar_s1210()

    # --- previdência complementar ----------------------------------------
    def test_previdencia_complementar_por_tipo(self):
        self.contract.l10n_br_esocial_cnpj_prev_compl = "11.444.777/0001-61"
        s1210 = self._holerite(descontos=[("46", 150.0), ("62", 80.0), ("64", 40.0)])
        self.assertEqual(
            s1210._info_ir_complem()["previd"],
            {
                ("1", CNPJ_ENTIDADE): {"mensal": 150.0, "decimo": 0.0},
                ("2", CNPJ_ENTIDADE): {"mensal": 80.0, "decimo": 0.0},
                ("3", CNPJ_ENTIDADE): {"mensal": 40.0, "decimo": 0.0},
            },
        )

    def test_previdencia_sem_cnpj_da_entidade_e_recusada(self):
        payslip = self._holerite(descontos=[("46", 150.0)], gerar=False)
        with self.assertRaisesRegex(UserError, "Previdência Complementar"):
            payslip.action_esocial_gerar_s1210()

    # --- 13º salário -----------------------------------------------------
    def test_decimo_terceiro_usa_tp_rend_12(self):
        s1210 = self._holerite()
        pagamento = s1210.pagamento_ids
        self.assertEqual(s1210._tp_rend(pagamento), "11")
        pagamento.per_ref = "2024"
        self.assertEqual(s1210._tp_rend(pagamento), "12")

    # --- categoria / código de receita -----------------------------------
    def test_codigo_de_receita_por_categoria(self):
        s1210 = self._holerite()
        self.assertEqual(s1210._tp_cr(), "056107")
        s1210.employee_id.l10n_br_esocial_categoria_id = self.env.ref(
            "l10n_br_esocial.cat_trab_104"
        )
        self.assertEqual(s1210._tp_cr(), "056108")

    # --- XML -------------------------------------------------------------
    def test_xml_na_ordem_do_leiaute(self):
        if not HAS_ESOCIALLIB:
            self.skipTest("esociallib não instalada")
        self.contract.write(
            {
                "l10n_br_esocial_cnpj_oper_saude": CNPJ_OPERADORA,
                "l10n_br_esocial_reg_ans": "123456",
                "l10n_br_esocial_cnpj_prev_compl": CNPJ_ENTIDADE,
            }
        )
        self._parente(
            l10n_br_esocial_pensao_alimenticia=True,
            l10n_br_esocial_vlr_saude=100.0,
        )
        self._dependente_irrf(name="Filho de Teste", l10n_br_esocial_cpf=CPF_FILHO)
        self.employee.l10n_br_irrf_dependentes = 1
        s1210 = self._holerite(
            descontos=[("51", 620.0), ("67", 300.0), ("46", 150.0)], irrf=True
        )
        raiz = self._xml(s1210)
        grupo = raiz.find(".//e:ideBenef/e:infoIRComplem", NS)
        self.assertIsNotNone(grupo)

        def tags(el):
            return [filho.tag.split("}")[1] for filho in el]

        self.assertEqual(tags(grupo), ["infoDep", "infoIRCR", "planSaude"])
        # depIRRF só admite "S" no XSD: o parente que só recebe pensão não o leva
        self.assertEqual(
            tags(grupo.find("e:infoDep", NS)), ["cpfDep", "dtNascto", "nome"]
        )
        self.assertEqual(
            tags(raiz.find(".//e:ideBenef", NS)),
            ["cpfBenef", "infoPgto", "infoIRComplem"],
        )
        cr = grupo.find("e:infoIRCR", NS)
        self.assertEqual(tags(cr), ["tpCR", "dedDepen", "penAlim", "previdCompl"])
        self.assertEqual(
            tags(cr.find("e:penAlim", NS)), ["tpRend", "cpfDep", "vlrDedPenAlim"]
        )
        self.assertEqual(
            tags(cr.find("e:previdCompl", NS)), ["tpPrev", "cnpjEntidPC", "vlrDedPC"]
        )
        plano = grupo.find("e:planSaude", NS)
        self.assertEqual(
            tags(plano), ["cnpjOper", "regANS", "vlrSaudeTit", "infoDepSau"]
        )
        # titular = 300 - 100 do dependente
        self.assertEqual(plano.find("e:vlrSaudeTit", NS).text, "200.00")
        self.assertEqual(cr.find("e:penAlim/e:vlrDedPenAlim", NS).text, "620.00")

    def test_xml_valido_contra_o_xsd_quando_disponivel(self):
        if not HAS_ESOCIALLIB:
            self.skipTest("esociallib não instalada")
        from esociallib.validators import validate_xsd

        self.contract.write(
            {
                "l10n_br_esocial_cnpj_oper_saude": CNPJ_OPERADORA,
                "l10n_br_esocial_cnpj_prev_compl": CNPJ_ENTIDADE,
            }
        )
        self._parente(l10n_br_esocial_pensao_alimenticia=True)
        self._dependente_irrf(name="Filho de Teste", l10n_br_esocial_cpf=CPF_FILHO)
        self.employee.l10n_br_irrf_dependentes = 1
        s1210 = self._holerite(
            descontos=[("51", 620.0), ("67", 300.0), ("46", 150.0)], irrf=True
        )
        try:
            erros = validate_xsd(s1210.evento_id.xml_envio, "S-1210")
        except FileNotFoundError:
            self.skipTest(
                "SKIP EXPLÍCITO: XSDs oficiais S-1.3 ausentes da esociallib; "
                "a validação contra o XSD não rodou neste ambiente"
            )
        self.assertEqual([e for e in erros if "Signature" not in e], [])

    # --- tpPgto ----------------------------------------------------------
    def test_dominio_do_tp_pgto_e_o_do_leiaute_s13(self):
        """evtPgtos.xsd S-1.3: 1=S-1200, 2=S-2299, 3=S-2399, 4=S-1202, 5=S-1207."""
        selecao = dict(
            self.env["l10n_br.esocial.s1210.pagamento"]._fields["tp_pgto"].selection
        )
        self.assertEqual(set(selecao), {"1", "2", "3", "4", "5"})
        self.assertIn("S-2299", selecao["2"])
        self.assertIn("S-2399", selecao["3"])
        self.assertIn("S-1202", selecao["4"])
        self.assertIn("S-1207", selecao["5"])
