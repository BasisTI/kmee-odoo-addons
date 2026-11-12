# Copyright 2026 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

"""S-2200 (TG-101): os campos vêm do cadastro do empregado e do contrato."""

from lxml import etree

from odoo.exceptions import UserError

from .test_intermediarios import HAS_ESOCIALLIB, TestESocialIntermediarioBase

NS = {"e": "http://www.esocial.gov.br/schema/evt/evtAdmissao/v_S_01_03_00"}


class TestS2200Cadastro(TestESocialIntermediarioBase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.s2200 = cls.env["l10n_br.esocial.s2200"].create(
            {
                "employee_id": cls.employee.id,
                "contract_id": cls.contract.id,
                "company_id": cls.company.id,
            }
        )
        cls.tipo_filho = cls.env["l10n_br.esocial.tipo.dependente"].search(
            [("codigo", "=", "03"), ("dt_fim", "=", False)], limit=1
        )
        cls.tipo_outros = cls.env["l10n_br.esocial.tipo.dependente"].search(
            [("codigo", "=", "99"), ("dt_fim", "=", False)], limit=1
        )
        cls.relacao = cls.env.ref("hr_employee_relative.relation_child")

    def _dependente(self, **extra):
        vals = {
            "employee_id": self.employee.id,
            "relation_id": self.relacao.id,
            "name": "Filha de Teste",
            "date_of_birth": "2015-03-20",
            "l10n_br_esocial_tp_dep_id": self.tipo_filho.id,
            "l10n_br_esocial_cpf": "529.982.247-25",
            "l10n_br_esocial_dep_irrf": True,
            "l10n_br_esocial_dep_sf": True,
        }
        vals.update(extra)
        return self.env["hr.employee.relative"].create(vals)

    def _xml(self):
        xml = self.s2200._gerar_xml()
        return etree.fromstring(xml.encode("utf-8"))

    # --- trabalhador -----------------------------------------------------
    def test_trabalhador_vem_do_cadastro(self):
        self.employee.write(
            {
                "gender": "female",
                "birthday": "1985-11-02",
                "ethnicity": self.env.ref("l10n_br_hr.ethnicity_3").id,
                "l10n_br_esocial_grau_instr": "09",
            }
        )
        data = self.s2200._to_esociallib_dict()
        self.assertEqual(data["sexo"], "F")
        self.assertEqual(data["raca_cor"], 3)
        self.assertEqual(data["grau_instr"], "09")
        self.assertEqual(data["dt_nascto"], "1985-11-02")

    def test_campo_faltante_recusa_em_vez_de_valor_fixo(self):
        casos = {
            "raça/cor": {"ethnicity": False},
            "raça/cor não informada no leiaute": {
                "ethnicity": self.env["hr.ethnicity"]
                .create({"code": "9", "name": "Fora da tabela"})
                .id
            },
            "grau de instrução": {"l10n_br_esocial_grau_instr": False},
            "nascimento": {"birthday": False},
            "sexo ausente": {"gender": False},
            "sexo outro": {"gender": "other"},
        }
        for rotulo, vals in casos.items():
            with self.subTest(rotulo):
                original = {k: self.employee[k] for k in vals}
                restaurar = {
                    k: (v.id if hasattr(v, "id") else v) for k, v in original.items()
                }
                self.employee.write(vals)
                with self.assertRaises(UserError):
                    self.s2200._to_esociallib_dict()
                self.employee.write(restaurar)

    # --- vínculo ---------------------------------------------------------
    def test_cnpj_do_sindicato_vem_do_contrato(self):
        data = self.s2200._to_esociallib_dict()
        self.assertEqual(data["cnpj_sind_categ_prof"], "11222333000181")

    def test_sem_sindicato_ou_cnpj_invalido_recusa(self):
        self.contract.partner_union = False
        with self.assertRaises(UserError):
            self.s2200._to_esociallib_dict()
        # Dígito verificador errado: o ORM não deixaria gravar, então vai por SQL.
        self.env.cr.execute(
            "UPDATE res_partner SET vat = %s WHERE id = %s",
            ("11.222.333/0001-82", self.sindicato.id),
        )
        self.sindicato.invalidate_recordset(["vat"])
        self.contract.partner_union = self.sindicato
        with self.assertRaises(UserError):
            self.s2200._to_esociallib_dict()

    def test_jornada_vem_do_contrato(self):
        data = self.s2200._to_esociallib_dict()
        self.assertEqual(data["qtd_hrs_sem"], "40.00")
        self.assertEqual(data["tp_jornada"], 4)
        self.assertEqual(data["tmp_parc"], 0)
        self.assertEqual(data["hor_noturno"], "N")
        self.assertTrue(
            data["dsc_jorn"].startswith("Segunda: 08:00-12:00, 13:00-17:00")
        )

    def test_jornada_noturna(self):
        calendario = self.env["resource.calendar"].create(
            {
                "name": "Noturno",
                "attendance_ids": [
                    (
                        0,
                        0,
                        {
                            "name": "Noite",
                            "dayofweek": "0",
                            "hour_from": 19.0,
                            "hour_to": 23.0,
                        },
                    )
                ],
            }
        )
        self.contract.resource_calendar_id = calendario
        data = self.s2200._to_esociallib_dict()
        self.assertEqual(data["hor_noturno"], "S")
        self.assertEqual(data["qtd_hrs_sem"], "4.00")
        self.assertEqual(data["dsc_jorn"], "Segunda: 19:00-23:00")

    def test_jornada_sem_tipo_recusa(self):
        self.contract.l10n_br_esocial_tp_jornada = False
        with self.assertRaises(UserError):
            self.s2200._to_esociallib_dict()

    def test_local_de_trabalho_e_estabelecimento_do_empregador(self):
        data = self.s2200._to_esociallib_dict()
        self.assertEqual(data["tp_insc_local"], 1)
        self.assertEqual(
            data["nr_insc_local"],
            "".join(filter(str.isdigit, self.company.partner_id.vat)),
        )

    def test_local_de_trabalho_invalido_recusa(self):
        outro = self.env["res.partner"].create(
            {"name": "Outro grupo", "vat": "11.444.777/0001-61"}
        )
        self.employee.address_id = outro
        with self.assertRaises(UserError):  # raiz diferente da do empregador
            self.s2200._to_esociallib_dict()
        self.employee.address_id = self.env["res.partner"].create({"name": "Sem CNPJ"})
        with self.assertRaises(UserError):
            self.s2200._to_esociallib_dict()

    # --- dependentes -----------------------------------------------------
    def test_sem_dependentes_nao_envia_grupo(self):
        self.assertEqual(self.s2200._to_esociallib_dict()["dependentes"], [])

    def test_parente_sem_tipo_nao_e_dependente(self):
        self._dependente(l10n_br_esocial_tp_dep_id=False)
        self.assertEqual(self.s2200._to_esociallib_dict()["dependentes"], [])

    def test_dependente_vem_do_cadastro(self):
        self._dependente()
        (dep,) = self.s2200._to_esociallib_dict()["dependentes"]
        self.assertEqual(
            dep,
            {
                "tp_dep": "03",
                "nm_dep": "Filha de Teste",
                "dt_nascto": "2015-03-20",
                "cpf_dep": "52998224725",
                "dep_irrf": "S",
                "dep_sf": "S",
                "inc_trab": "N",
                "descr_dep": "",
            },
        )

    def test_dependente_incompleto_ou_repetido_recusa(self):
        rel = self._dependente()
        casos = {
            "sem nascimento": {"date_of_birth": False},
            "IRRF sem CPF": {"l10n_br_esocial_cpf": False},
            "CPF inválido": {"l10n_br_esocial_cpf": "529.982.247-26"},
        }
        for rotulo, vals in casos.items():
            with self.subTest(rotulo):
                antes = {k: rel[k] for k in vals}
                rel.write(vals)
                with self.assertRaises(UserError):
                    self.s2200._to_esociallib_dict()
                rel.write(antes)
        self._dependente(name="Outra Filha")  # mesmo CPF
        with self.assertRaises(UserError):
            self.s2200._to_esociallib_dict()

    def test_dependente_tipo_99_exige_descricao(self):
        rel = self._dependente(
            l10n_br_esocial_tp_dep_id=self.tipo_outros.id,
            l10n_br_esocial_dep_irrf=False,
            l10n_br_esocial_cpf=False,
        )
        with self.assertRaises(UserError):
            self.s2200._to_esociallib_dict()
        rel.l10n_br_esocial_descr_dep = "Sobrinho sob guarda de fato"
        (dep,) = self.s2200._to_esociallib_dict()["dependentes"]
        self.assertEqual(dep["descr_dep"], "Sobrinho sob guarda de fato")
        self.assertEqual(dep["cpf_dep"], "")

    # --- XML -------------------------------------------------------------
    def test_xml_campo_a_campo(self):
        if not HAS_ESOCIALLIB:
            self.skipTest("esociallib não instalada")
        self.employee.write(
            {
                "gender": "female",
                "birthday": "1985-11-02",
                "ethnicity": self.env.ref("l10n_br_hr.ethnicity_3").id,
                "l10n_br_esocial_grau_instr": "09",
            }
        )
        self._dependente()
        raiz = self._xml()

        def valor(caminho):
            return raiz.findtext(caminho, namespaces=NS)

        self.assertEqual(valor(".//e:trabalhador/e:sexo"), "F")
        self.assertEqual(valor(".//e:trabalhador/e:racaCor"), "3")
        self.assertEqual(valor(".//e:trabalhador/e:grauInstr"), "09")
        self.assertEqual(valor(".//e:nascimento/e:dtNascto"), "1985-11-02")
        self.assertEqual(
            valor(".//e:infoCeletista/e:cnpjSindCategProf"), "11222333000181"
        )
        self.assertEqual(valor(".//e:localTrabGeral/e:tpInsc"), "1")
        self.assertEqual(
            valor(".//e:localTrabGeral/e:nrInsc"),
            "".join(filter(str.isdigit, self.company.partner_id.vat)),
        )
        self.assertEqual(valor(".//e:horContratual/e:qtdHrsSem"), "40.00")
        self.assertEqual(valor(".//e:horContratual/e:tpJornada"), "4")
        self.assertEqual(valor(".//e:horContratual/e:tmpParc"), "0")
        self.assertEqual(valor(".//e:horContratual/e:horNoturno"), "N")
        self.assertIn("Sexta: 08:00-12:00", valor(".//e:horContratual/e:dscJorn"))
        dependente = raiz.find(".//e:trabalhador/e:dependente", NS)
        self.assertEqual(
            [(el.tag.split("}")[1], el.text) for el in dependente],
            [
                ("tpDep", "03"),
                ("nmDep", "Filha de Teste"),
                ("dtNascto", "2015-03-20"),
                ("cpfDep", "52998224725"),
                ("depIRRF", "S"),
                ("depSF", "S"),
                ("incTrab", "N"),
            ],
        )

    def test_xml_valido_contra_o_xsd_quando_disponivel(self):
        if not HAS_ESOCIALLIB:
            self.skipTest("esociallib não instalada")
        from esociallib.validators import validate_xsd

        self._dependente()
        xml = self.s2200._gerar_xml()
        try:
            erros = validate_xsd(xml, "S-2200")
        except FileNotFoundError:
            self.skipTest("XSDs oficiais ausentes da esociallib")
        self.assertEqual([e for e in erros if "Signature" not in e], [])
