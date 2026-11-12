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
        self.estagiario.l10n_br_esocial_categoria_id = self._categoria("701")
        self.contrato.date_end = False
        self.estagiario.write(
            {"job_id": False, "country_of_birth": False, "birthday": False}
        )
        with self.assertRaises(UserError) as erro:
            self._s2300()._to_esociallib_dict()
        texto = erro.exception.args[0]
        for trecho in (
            "Cargo",
            "País de Nascimento",
            "Data de Nascimento",
        ):
            self.assertIn(trecho, texto)

    def _categoria(self, codigo):
        return self.env["l10n_br.esocial.categoria.trabalhador"].search(
            [("codigo", "=", codigo)], limit=1
        )

    def test_s2300_cbo_ausente_recusa_onde_o_cargo_e_obrigatorio(self):
        self.estagiario.job_id.cbo_id = False
        self.estagiario.l10n_br_esocial_categoria_id = self._categoria("701")
        with self.assertRaisesRegex(UserError, "CBO"):
            self._s2300()._to_esociallib_dict()

    def test_s2300_cargo_opcional_em_901_903_904_906(self):
        self.estagiario.job_id.cbo_id = False
        data = self._s2300()._to_esociallib_dict()  # 901 sem CBO: sem cargoFuncao
        self.assertNotIn("nm_cargo", data)
        self.assertNotIn("cod_cbo", data)
        self.estagiario.job_id = False
        self.assertNotIn("nm_cargo", self._s2300()._to_esociallib_dict())

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
        self.assertNotIn("cod_categ", data)  # exclusivo com a matrícula
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
        self.assertNotIn("cod_categ", data)  # exclusivo com a matrícula
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

    # --- regras de preenchimento do leiaute (TG-102 r2) --------------------
    def _raiz_ide(self, registro, ns):
        raiz = self._arvore(registro)
        ide = raiz.find(".//e:ideTrabSemVinculo", {"e": ns})
        return [etree.QName(el).localname for el in ide]

    def test_s2306_e_s2399_identificam_so_por_cpf_e_matricula_no_xml(self):
        if not HAS_ESOCIALLIB:
            self.skipTest("esociallib não instalada")
        for registro, ns in ((self._s2306(), NS_ALT), (self._s2399(), NS_TERM)):
            with self.subTest(registro._name):
                self.assertEqual(self._raiz_ide(registro, ns), ["cpfTrab", "matricula"])

    def test_local_so_nas_categorias_do_leiaute(self):
        self.assertEqual(self._s2300()._to_esociallib_dict()["tp_insc_local"], 1)
        for codigo in ("701", "308", "903"):
            with self.subTest(codigo):
                self.estagiario.l10n_br_esocial_categoria_id = self._categoria(codigo)
                self.contrato.l10n_br_esocial_nat_atividade = "1"
                data = self._s2300()._to_esociallib_dict()
                self.assertNotIn("tp_insc_local", data)
                self.assertNotIn("nr_insc_local", data)

    def test_local_obrigatorio_ate_2024_facultativo(self):
        self.estagiario.address_id = self.env["res.partner"].create(
            {"name": "Sem CNPJ"}
        )
        with self.assertRaises(UserError):
            self._s2300()._to_esociallib_dict()
        self.contrato.date_start = "2023-12-01"
        self.assertNotIn(
            "tp_insc_local", self._s2300(cad_ini="N")._to_esociallib_dict()
        )

    def test_remuneracao_obrigatoria_em_721_722_771_906(self):
        self.contrato.wage = 0
        self.contrato.l10n_br_esocial_dt_opc_fgts = self.inicio
        for codigo in ("721", "722", "771", "906"):
            with self.subTest(codigo):
                self.estagiario.l10n_br_esocial_categoria_id = self._categoria(codigo)
                self.contrato.l10n_br_esocial_nat_estagio = "N"
                with self.assertRaisesRegex(UserError, "remuneração"):
                    self._s2300()._to_esociallib_dict()
        # categoria em que é opcional: sai sem o grupo
        self.estagiario.l10n_br_esocial_categoria_id = self.cat_901
        self.assertNotIn("vr_sal_fx", self._s2300()._to_esociallib_dict())

    def test_fgts_obrigatorio_na_721(self):
        self.estagiario.l10n_br_esocial_categoria_id = self._categoria("721")
        with self.assertRaisesRegex(UserError, "Opção pelo FGTS"):
            self._s2300()._to_esociallib_dict()
        self.contrato.l10n_br_esocial_dt_opc_fgts = self.inicio
        data = self._s2300()._to_esociallib_dict()
        self.assertEqual(data["dt_opc_fgts"], str(self.inicio))
        self.assertNotIn("nat_atividade", data)
        # nas demais categorias o grupo não existe
        self.estagiario.l10n_br_esocial_categoria_id = self.cat_901
        self.assertNotIn("dt_opc_fgts", self._s2300()._to_esociallib_dict())

    def test_fgts_721_no_xml_e_xsd(self):
        if not HAS_ESOCIALLIB:
            self.skipTest("esociallib não instalada")
        self.estagiario.l10n_br_esocial_categoria_id = self._categoria("721")
        self.contrato.l10n_br_esocial_dt_opc_fgts = self.inicio
        s2300 = self._s2300()
        raiz = self._arvore(s2300)
        compl = raiz.find(".//e:infoComplementares", {"e": NS_INI})
        self.assertEqual(
            [etree.QName(el).localname for el in compl],
            ["cargoFuncao", "remuneracao", "FGTS", "localTrabGeral"],
        )
        self._valida_no_xsd(s2300, "S-2300")

    def test_906_nao_emite_agente_nem_supervisor(self):
        self.estagiario.l10n_br_esocial_categoria_id = self.env.ref(
            "l10n_br_esocial.cat_trab_906"
        )
        data = self._s2300()._to_esociallib_dict()
        self.assertFalse(data["estagiario"]["cnpj_age_integ"])
        self.assertFalse(data["estagiario"]["cpf_supervisor"])
        if HAS_ESOCIALLIB:
            raiz = self._arvore(self._s2300())
            self.assertIsNone(raiz.find(".//e:ageIntegracao", {"e": NS_INI}))
            self.assertIsNone(raiz.find(".//e:supervisorEstagio", {"e": NS_INI}))
        # na 901 vão os dois
        self.estagiario.l10n_br_esocial_categoria_id = self.cat_901
        data = self._s2300()._to_esociallib_dict()
        self.assertTrue(data["estagiario"]["cnpj_age_integ"])
        self.assertTrue(data["estagiario"]["cpf_supervisor"])

    def test_pensao_opcional_ate_21_04_2019(self):
        self.estagiario.l10n_br_esocial_categoria_id = self._categoria("202")
        self.contrato.date_start = "2018-06-01"
        self.contrato.l10n_br_esocial_nat_atividade = "1"
        antigo = self._s2399(dt_term="2019-04-21")
        self.assertNotIn("pens_alim", antigo._to_esociallib_dict())
        self.assertEqual(
            antigo.write({"pens_alim": "0"})
            and antigo._to_esociallib_dict()["pens_alim"],
            0,
        )
        with self.assertRaisesRegex(UserError, "Pensão Alimentícia"):
            self._s2399(dt_term="2019-04-22")._to_esociallib_dict()

    def test_s2306_alteracao_alem_de_180_dias_recusa(self):
        hoje = fields.Date.context_today(self.contrato)
        self.contrato.date_end = hoje + timedelta(days=400)
        with self.assertRaisesRegex(UserError, "180"):
            self._s2306(dt_alteracao=hoje + timedelta(days=181))._to_esociallib_dict()
        self._s2306(dt_alteracao=hoje + timedelta(days=180))._to_esociallib_dict()

    def test_cad_ini_contra_inicio_dos_eventos_nao_periodicos(self):
        with self.assertRaisesRegex(UserError, "Início dos Eventos Não Periódicos"):
            self._s2300(cad_ini="S")._to_esociallib_dict()
        self.company.l10n_br_esocial_dt_ini_nao_periodicos = self.inicio + timedelta(
            days=5
        )
        with self.assertRaisesRegex(UserError, "anterior ao início dos eventos"):
            self.company.l10n_br_esocial_dt_ini_nao_periodicos = self.inicio
            self._s2300(cad_ini="S")._to_esociallib_dict()
        self.company.l10n_br_esocial_dt_ini_nao_periodicos = self.inicio + timedelta(
            days=5
        )
        self.assertEqual(self._s2300(cad_ini="S")._to_esociallib_dict()["cad_ini"], "S")
        with self.assertRaisesRegex(UserError, "use Cadastramento inicial"):
            self._s2300(cad_ini="N")._to_esociallib_dict()

    def test_mensagens_do_s2300_nao_falam_em_s2200_nem_empregado(self):
        self.estagiario.write(
            {
                "ethnicity": self.env.ref("l10n_br_hr.ethnicity_6").id,
                "gender": False,
                "birthday": False,
                "l10n_br_esocial_grau_instr": False,
            }
        )
        with self.assertRaises(UserError) as erro:
            self._s2300()._to_esociallib_dict()
        texto = erro.exception.args[0]
        self.assertNotIn("S-2200", texto)
        self.assertNotIn("Empregado", texto)
        self.assertIn("S-2300", texto)

    def test_s2300_estagio_sem_dados_recusa_com_todos_os_motivos(self):
        self.contrato.write(
            {
                "l10n_br_esocial_nat_estagio": False,
                "l10n_br_esocial_niv_estagio": False,
                "l10n_br_esocial_inst_ensino_id": False,
            }
        )
        with self.assertRaises(UserError) as erro:
            self._s2300()._to_esociallib_dict()
        for trecho in (
            "Natureza do Estágio",
            "Nível do Estágio",
            "Instituição de Ensino",
        ):
            self.assertIn(trecho, erro.exception.args[0])
