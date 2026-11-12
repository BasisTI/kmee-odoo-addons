# Copyright 2026 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

"""S-2300, S-2306 e S-2399 (TG-102): trabalhador sem vínculo, como o estagiário."""

from datetime import timedelta

from lxml import etree

from odoo import fields
from odoo.exceptions import UserError

from .test_intermediarios import HAS_ESOCIALLIB, TestESocialIntermediarioBase

NS_INI = "http://www.esocial.gov.br/schema/evt/evtTSVInicio/v_S_01_03_00"
NS_ALT = "http://www.esocial.gov.br/schema/evt/evtTSVAltContr/v_S_01_03_00"
NS_TERM = "http://www.esocial.gov.br/schema/evt/evtTSVTermino/v_S_01_03_00"


class TestTSVE(TestESocialIntermediarioBase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        hoje = fields.Date.context_today(cls.env["res.partner"])
        cls.inicio = hoje - timedelta(days=30)
        cls.fim = hoje + timedelta(days=300)
        cls.cat_901 = cls.env.ref("l10n_br_esocial.cat_trab_901")
        brasil = cls.env.ref("base.br")
        if not brasil.bc_code:
            brasil.bc_code = "1058"
        cbo = cls.env["l10n_br_hr.cbo"].create({"code": "351105", "name": "Estagiário"})
        cargo = cls.env["hr.job"].create({"name": "Estagiário de TI", "cbo_id": cbo.id})
        cls.inst = cls.env["res.partner"].create(
            {"name": "Faculdade Fictícia", "vat": "45.000.001/0001-74"}
        )
        cls.agente = cls.env["res.partner"].create(
            {"name": "Agente de Integração Fictício", "vat": "55.000.001/0001-28"}
        )
        cls.supervisor = cls.env["hr.employee"].create(
            {"name": "Supervisora de Teste", "cnpj_cpf": "529.982.247-25"}
        )
        cls.estagiario = cls.env["hr.employee"].create(
            {
                "name": "Estagiário de Teste",
                "cnpj_cpf": "076.166.929-41",
                "l10n_br_esocial_matricula": "EST001",
                "l10n_br_esocial_categoria_id": cls.cat_901.id,
                "gender": "female",
                "birthday": "2003-04-10",
                "ethnicity": cls.env.ref("l10n_br_hr.ethnicity_3").id,
                "l10n_br_esocial_grau_instr": "08",
                "country_id": brasil.id,
                "country_of_birth": brasil.id,
                "job_id": cargo.id,
                "address_id": cls.company.partner_id.id,
            }
        )
        cls.contrato = cls.env["hr.contract"].create(
            {
                "name": "Termo de estágio",
                "employee_id": cls.estagiario.id,
                "wage": 1500.0,
                "date_start": cls.inicio,
                "date_end": cls.fim,
                "state": "open",
                "l10n_br_esocial_nat_estagio": "N",
                "l10n_br_esocial_niv_estagio": "4",
                "l10n_br_esocial_area_atuacao": "Tecnologia da informação",
                "l10n_br_esocial_nr_apolice": "AP-123",
                "l10n_br_esocial_inst_ensino_id": cls.inst.id,
                "l10n_br_esocial_age_integ_id": cls.agente.id,
                "l10n_br_esocial_supervisor_id": cls.supervisor.id,
            }
        )

    def _s2300(self, **extra):
        vals = {
            "employee_id": self.estagiario.id,
            "contract_id": self.contrato.id,
            "company_id": self.company.id,
        }
        vals.update(extra)
        return self.env["l10n_br.esocial.s2300"].create(vals)

    def _s2306(self, **extra):
        vals = {
            "employee_id": self.estagiario.id,
            "contract_id": self.contrato.id,
            "company_id": self.company.id,
            "dt_alteracao": self.inicio + timedelta(days=10),
        }
        vals.update(extra)
        return self.env["l10n_br.esocial.s2306"].create(vals)

    def _s2399(self, **extra):
        vals = {
            "employee_id": self.estagiario.id,
            "contract_id": self.contrato.id,
            "company_id": self.company.id,
            "dt_term": self.inicio + timedelta(days=20),
        }
        vals.update(extra)
        return self.env["l10n_br.esocial.s2399"].create(vals)

    def _arvore(self, registro):
        return etree.fromstring(registro._gerar_xml().encode("utf-8"))

    def _valida_no_xsd(self, registro, tipo):
        """Valida no XSD oficial; sem ele (o CI não o tem) é skip explícito."""
        from esociallib.validators import validate_xsd

        try:
            erros = validate_xsd(registro._gerar_xml(), tipo)
        except FileNotFoundError:
            self.skipTest(
                "SKIP EXPLÍCITO: XSDs oficiais S-1.3 ausentes da esociallib; "
                "a validação contra o XSD não rodou neste ambiente"
            )
        self.assertEqual([e for e in erros if "Signature" not in e], [])

    # --- categoria define o evento ----------------------------------------
    def test_s2200_recusa_categoria_sem_vinculo(self):
        s2200 = self.env["l10n_br.esocial.s2200"].create(
            {
                "employee_id": self.estagiario.id,
                "contract_id": self.contrato.id,
                "company_id": self.company.id,
            }
        )
        with self.assertRaisesRegex(UserError, "S-2300"):
            s2200._to_esociallib_dict()

    def test_s2206_e_s2299_recusam_categoria_sem_vinculo(self):
        s2206 = self.env["l10n_br.esocial.s2206"].create(
            {
                "employee_id": self.estagiario.id,
                "contract_id": self.contrato.id,
                "dt_alteracao": self.inicio,
                "company_id": self.company.id,
            }
        )
        with self.assertRaisesRegex(UserError, "S-2306"):
            s2206._to_esociallib_dict()
        s2299 = self.env["l10n_br.esocial.s2299"].create(
            {
                "employee_id": self.estagiario.id,
                "contract_id": self.contrato.id,
                "dt_deslig": self.fim,
                "motivo_desligamento_id": self.mot_deslig_02.id,
                "company_id": self.company.id,
            }
        )
        with self.assertRaisesRegex(UserError, "S-2399"):
            s2299._to_esociallib_dict()

    def test_tsve_recusa_categoria_com_vinculo(self):
        self.estagiario.l10n_br_esocial_categoria_id = self.cat_101
        for registro in (self._s2300(), self._s2306(), self._s2399()):
            with self.subTest(registro._name):
                with self.assertRaisesRegex(UserError, "S-2200|S-2206|S-2299"):
                    registro._to_esociallib_dict()

    def test_categoria_com_grupo_proprio_nao_suportado_recusa(self):
        for codigo in ("304", "305", "401", "410"):
            with self.subTest(codigo):
                self.estagiario.l10n_br_esocial_categoria_id = self.env[
                    "l10n_br.esocial.categoria.trabalhador"
                ].search([("codigo", "=", codigo)], limit=1)
                with self.assertRaisesRegex(UserError, "ainda não gera"):
                    self._s2300()._to_esociallib_dict()

    # --- S-2300 -----------------------------------------------------------
    def test_s2300_vem_do_cadastro(self):
        data = self._s2300()._to_esociallib_dict()
        self.assertEqual(data["cod_categ"], "901")
        self.assertEqual(data["cpf_trab"], "07616692941")
        self.assertEqual(data["matricula"], "EST001")
        self.assertEqual(data["sexo"], "F")
        self.assertEqual(data["raca_cor"], 3)
        self.assertEqual(data["grau_instr"], "08")
        self.assertEqual(data["dt_nascto"], "2003-04-10")
        self.assertEqual((data["pais_nascto"], data["pais_nac"]), ("105", "105"))
        self.assertEqual(data["dt_inicio"], str(self.inicio))
        self.assertEqual(data["cad_ini"], "N")
        self.assertEqual(data["nm_cargo"], "Estagiário de TI")
        self.assertEqual(data["cod_cbo"], "351105")
        self.assertEqual(data["vr_sal_fx"], "1500.00")
        self.assertNotIn("nat_atividade", data)  # proibido na categoria 901
        self.assertEqual(
            data["estagiario"],
            {
                "nat_estagio": "N",
                "niv_estagio": "4",
                "area_atuacao": "Tecnologia da informação",
                "nr_apol": "AP-123",
                "dt_prev_term": str(self.fim),
                "cnpj_inst_ensino": "45000001000174",
                "cnpj_age_integ": "55000001000128",
                "cpf_supervisor": "52998224725",
            },
        )

    def test_s2300_dado_faltante_recusa_com_todos_os_motivos(self):
        self.estagiario.write(
            {"job_id": False, "country_of_birth": False, "birthday": False}
        )
        self.contrato.write(
            {
                "l10n_br_esocial_nat_estagio": False,
                "l10n_br_esocial_niv_estagio": False,
                "l10n_br_esocial_inst_ensino_id": False,
            }
        )
        with self.assertRaises(UserError) as erro:
            self._s2300()._to_esociallib_dict()
        texto = erro.exception.args[0]
        for trecho in (
            "Cargo",
            "País de Nascimento",
            "Data de Nascimento",
            "Natureza do Estágio",
            "Nível do Estágio",
            "Instituição de Ensino",
        ):
            self.assertIn(trecho, texto)

    def test_s2300_cbo_ausente_recusa(self):
        self.estagiario.job_id.cbo_id = False
        with self.assertRaisesRegex(UserError, "CBO"):
            self._s2300()._to_esociallib_dict()

    def test_s2300_instituicao_sem_cnpj_valido_recusa(self):
        self.inst.vat = False
        with self.assertRaisesRegex(UserError, "Instituição de Ensino"):
            self._s2300()._to_esociallib_dict()

    def test_s2300_termino_previsto_obrigatorio_e_posterior_ao_inicio(self):
        for fim in (False, self.inicio):
            with self.subTest(fim=fim):
                self.contrato.date_end = fim
                with self.assertRaisesRegex(UserError, "término"):
                    self._s2300()._to_esociallib_dict()
        self.contrato.date_end = self.fim

    def test_s2300_inicio_longe_no_futuro_recusa(self):
        self.contrato.date_start = fields.Date.context_today(self.contrato) + timedelta(
            days=31
        )
        self.contrato.date_end = self.fim + timedelta(days=60)
        with self.assertRaisesRegex(UserError, "dias à frente"):
            self._s2300()._to_esociallib_dict()

    def test_s2300_906_exige_natureza_nao_obrigatoria(self):
        self.estagiario.l10n_br_esocial_categoria_id = self.env.ref(
            "l10n_br_esocial.cat_trab_906"
        )
        self.contrato.l10n_br_esocial_nat_estagio = "O"
        with self.assertRaisesRegex(UserError, "906"):
            self._s2300()._to_esociallib_dict()
        self.contrato.l10n_br_esocial_nat_estagio = "N"
        self.assertEqual(self._s2300()._to_esociallib_dict()["cod_categ"], "906")

    def test_s2300_natureza_da_atividade_obrigatoria_em_731(self):
        self.estagiario.l10n_br_esocial_categoria_id = self.env[
            "l10n_br.esocial.categoria.trabalhador"
        ].search([("codigo", "=", "731")], limit=1)
        with self.assertRaisesRegex(UserError, "Natureza da Atividade"):
            self._s2300()._to_esociallib_dict()
        self.contrato.l10n_br_esocial_nat_atividade = "1"
        data = self._s2300()._to_esociallib_dict()
        self.assertEqual(data["nat_atividade"], 1)
        self.assertNotIn("estagiario", data)

    def test_s2300_sem_cargo_exigido_em_categoria_sem_estagio_ok(self):
        self.estagiario.l10n_br_esocial_categoria_id = self.env[
            "l10n_br.esocial.categoria.trabalhador"
        ].search([("codigo", "=", "701")], limit=1)
        self.contrato.date_end = False
        data = self._s2300()._to_esociallib_dict()
        self.assertEqual(data["cod_categ"], "701")
        self.assertNotIn("estagiario", data)

    def test_s2300_dependentes_do_cadastro(self):
        tipo = self.env["l10n_br.esocial.tipo.dependente"].search(
            [("codigo", "=", "03"), ("dt_fim", "=", False)], limit=1
        )
        self.env["hr.employee.relative"].create(
            {
                "employee_id": self.estagiario.id,
                "relation_id": self.env.ref("hr_employee_relative.relation_child").id,
                "name": "Filho de Teste",
                "date_of_birth": "2022-01-05",
                "l10n_br_esocial_tp_dep_id": tipo.id,
                "l10n_br_esocial_cpf": "529.982.247-25",
                "l10n_br_esocial_dep_irrf": True,
            }
        )
        data = self._s2300()._to_esociallib_dict()
        self.assertEqual(len(data["dependentes"]), 1)

    def test_s2300_xml_ordem_dos_elementos(self):
        """Ordem exigida pelo XSD, conferida sem os XSDs (que o CI não tem)."""
        if not HAS_ESOCIALLIB:
            self.skipTest("esociallib não instalada")
        raiz = self._arvore(self._s2300())
        ns = {"e": NS_INI}
        estagio = raiz.find(".//e:infoEstagiario", ns)
        self.assertEqual(
            [etree.QName(el).localname for el in estagio],
            [
                "natEstagio",
                "nivEstagio",
                "areaAtuacao",
                "nrApol",
                "dtPrevTerm",
                "instEnsino",
                "ageIntegracao",
                "supervisorEstagio",
            ],
        )
        compl = raiz.find(".//e:infoComplementares", ns)
        self.assertEqual(
            [etree.QName(el).localname for el in compl],
            ["cargoFuncao", "remuneracao", "infoEstagiario", "localTrabGeral"],
        )
        self.assertEqual(
            raiz.findtext(".//e:instEnsino/e:cnpjInstEnsino", namespaces=ns),
            "45000001000174",
        )
        self.assertIsNone(raiz.find(".//e:instEstagiario", ns))
        self.assertEqual(raiz.findtext(".//e:codCateg", namespaces=ns), "901")

    def test_s2300_xml_valido_contra_o_xsd_quando_disponivel(self):
        if not HAS_ESOCIALLIB:
            self.skipTest("esociallib não instalada")
        self._valida_no_xsd(self._s2300(), "S-2300")

    def test_s2300_gera_evento(self):
        if not HAS_ESOCIALLIB:
            self.skipTest("esociallib não instalada")
        evento = self._s2300().action_gerar_evento()
        self.assertEqual(evento.tipo, "S-2300")
        self.assertTrue(evento.id_evento)

    # --- S-2306 -----------------------------------------------------------
    def test_s2306_dict(self):
        data = self._s2306()._to_esociallib_dict()
        self.assertEqual(data["dt_alteracao"], str(self.inicio + timedelta(days=10)))
        self.assertEqual(data["cod_categ"], "901")
        self.assertEqual(data["estagiario"]["dt_prev_term"], str(self.fim))

    def test_s2306_alteracao_antes_do_inicio_recusa(self):
        with self.assertRaisesRegex(UserError, "anterior ao início"):
            self._s2306(
                dt_alteracao=self.inicio - timedelta(days=1)
            )._to_esociallib_dict()

    def test_s2306_xml_e_xsd(self):
        if not HAS_ESOCIALLIB:
            self.skipTest("esociallib não instalada")
        s2306 = self._s2306()
        raiz = self._arvore(s2306)
        ns = {"e": NS_ALT}
        self.assertEqual(
            [etree.QName(el).localname for el in raiz.find(".//e:infoEstagiario", ns)][
                :2
            ],
            ["natEstagio", "nivEstagio"],
        )
        self.assertEqual(s2306.action_gerar_evento().tipo, "S-2306")
        self._valida_no_xsd(s2306, "S-2306")

    # --- S-2399 -----------------------------------------------------------
    def test_s2399_dict(self):
        data = self._s2399()._to_esociallib_dict()
        self.assertEqual(data["dt_term"], str(self.inicio + timedelta(days=20)))
        self.assertEqual(data["cod_categ"], "901")
        self.assertNotIn("mtv_deslig_tsv", data)

    def test_s2399_motivo_so_na_categoria_721(self):
        with self.assertRaisesRegex(UserError, "721"):
            self._s2399(mtv_deslig_tsv="99")._to_esociallib_dict()
        self.estagiario.l10n_br_esocial_categoria_id = self.env[
            "l10n_br.esocial.categoria.trabalhador"
        ].search([("codigo", "=", "721")], limit=1)
        with self.assertRaisesRegex(UserError, "Motivo do Término"):
            self._s2399(pens_alim="0")._to_esociallib_dict()
        data = self._s2399(mtv_deslig_tsv="03", pens_alim="0")._to_esociallib_dict()
        self.assertEqual(data["mtv_deslig_tsv"], "03")
        self.assertEqual(data["pens_alim"], 0)

    def test_s2399_pensao_alimenticia(self):
        self.estagiario.l10n_br_esocial_categoria_id = self.env[
            "l10n_br.esocial.categoria.trabalhador"
        ].search([("codigo", "=", "202")], limit=1)
        with self.assertRaisesRegex(UserError, "Pensão Alimentícia"):
            self._s2399()._to_esociallib_dict()
        with self.assertRaisesRegex(UserError, "percentual"):
            self._s2399(pens_alim="1")._to_esociallib_dict()
        data = self._s2399(pens_alim="3", perc_aliment=10.0, vr_alim=250.0)
        data = data._to_esociallib_dict()
        self.assertEqual(
            (data["pens_alim"], data["perc_aliment"], data["vr_alim"]),
            (3, "10.00", "250.00"),
        )

    def test_s2399_pensao_proibida_em_901(self):
        with self.assertRaisesRegex(UserError, "Pensão Alimentícia"):
            self._s2399(pens_alim="0")._to_esociallib_dict()

    def test_s2399_datas(self):
        with self.assertRaisesRegex(UserError, "anterior ao início"):
            self._s2399(dt_term=self.inicio - timedelta(days=1))._to_esociallib_dict()
        hoje = fields.Date.context_today(self.contrato)
        with self.assertRaisesRegex(UserError, "dias à frente"):
            self._s2399(dt_term=hoje + timedelta(days=11))._to_esociallib_dict()

    def test_s2399_xml_e_xsd(self):
        if not HAS_ESOCIALLIB:
            self.skipTest("esociallib não instalada")
        s2399 = self._s2399()
        raiz = self._arvore(s2399)
        ns = {"e": NS_TERM}
        self.assertEqual(
            raiz.findtext(".//e:infoTSVTermino/e:dtTerm", namespaces=ns),
            str(self.inicio + timedelta(days=20)),
        )
        self.assertEqual(s2399.action_gerar_evento().tipo, "S-2399")
        self._valida_no_xsd(s2399, "S-2399")
