# Copyright 2024 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import logging

from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase
from odoo.tools import mute_logger

_logger = logging.getLogger(__name__)

try:
    import esociallib  # noqa: F401

    HAS_ESOCIALLIB = True
except ImportError:
    HAS_ESOCIALLIB = False


class TestESocialIntermediarioBase(TransactionCase):
    """Base class for intermediário tests with common setup."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Sem os XSDs oficiais na esociallib o gerador loga ERROR/WARNING por
        # desenho; isso e esperado nestes testes.
        mute = mute_logger(
            "odoo.addons.l10n_br_esocial.models.intermediarios.base_intermediario",
            "odoo.addons.l10n_br_esocial.models.intermediarios.s2200_admissao",
            "odoo.addons.l10n_br_esocial.models.intermediarios.tsv_mixin",
            "odoo.addons.l10n_br_esocial.models.intermediarios.trabalhador_mixin",
            "odoo.addons.l10n_br_esocial.models.esocial_lote",
        )
        mute.__enter__()
        cls.addClassCleanup(mute.__exit__, None, None, None)
        cls.company = cls.env.company
        partner = cls.company.partner_id
        if not partner.vat:
            partner.write({"vat": "02.546.716/0001-46"})

        cls.cat_101 = cls.env.ref("l10n_br_esocial.cat_trab_101")
        cls.class_trib = cls.env.ref("l10n_br_esocial.class_trib_01")
        cls.lotacao_tipo = cls.env.ref("l10n_br_esocial.lot_trib_01")
        cls.mot_afast_01 = cls.env.ref("l10n_br_esocial.mot_afast_01")
        cls.mot_deslig_02 = cls.env.ref("l10n_br_esocial.mot_deslig_02")

        cls.company.write(
            {
                "l10n_br_esocial_class_trib_id": cls.class_trib.id,
                "l10n_br_esocial_lotacao_id": cls.lotacao_tipo.id,
                "l10n_br_esocial_cod_lotacao": "LOT001",
            }
        )

        cls.employee = cls.env["hr.employee"].create(
            {
                "name": "Test eSocial Worker",
                "cnpj_cpf": "076.166.929-41",
                "l10n_br_esocial_matricula": "MAT001",
                "l10n_br_esocial_categoria_id": cls.cat_101.id,
                "gender": "male",
                "birthday": "1990-05-15",
                "ethnicity": cls.env.ref("l10n_br_hr.ethnicity_1").id,
                "l10n_br_esocial_grau_instr": "07",
            }
        )

        cls.sindicato = cls.env["res.partner"].create(
            {
                "name": "Sindicato dos Trabalhadores",
                "vat": "11.222.333/0001-81",
                "union_entity_code": "SIND001",
            }
        )
        cls.calendario = cls.env["resource.calendar"].create(
            {
                "name": "Padrão 40h",
                "attendance_ids": [
                    (
                        0,
                        0,
                        {
                            "name": "%s %s" % (dia, turno),
                            "dayofweek": dia,
                            "hour_from": ini,
                            "hour_to": fim,
                        },
                    )
                    for dia in ("0", "1", "2", "3", "4")
                    for turno, ini, fim in (("manhã", 8.0, 12.0), ("tarde", 13.0, 17.0))
                ],
            }
        )
        cls.contract = cls.env["hr.contract"].create(
            {
                "name": "Contrato CLT Test",
                "employee_id": cls.employee.id,
                "wage": 5000.00,
                "date_start": "2024-01-02",
                "state": "open",
                "partner_union": cls.sindicato.id,
                "resource_calendar_id": cls.calendario.id,
                "l10n_br_esocial_tp_jornada": "4",
            }
        )


class TestS1000(TestESocialIntermediarioBase):
    """Testes do intermediário S-1000 (Informações do Empregador)."""

    def test_s1000_dict_structure(self):
        """Dict do S-1000 deve conter campos obrigatórios."""
        s1000 = self.env["l10n_br.esocial.s1000"].create(
            {
                "operacao": "inclusao",
                "ini_valid": "2024-01",
                "company_id": self.company.id,
            }
        )
        data = s1000._to_esociallib_dict()
        self.assertEqual(data["operacao"], "inclusao")
        self.assertEqual(data["ini_valid"], "2024-01")
        self.assertIn("tp_insc", data)
        self.assertIn("nr_insc", data)
        self.assertIn("class_trib", data)

    def test_s1000_requires_class_trib(self):
        """Deve dar erro se empresa não tem classificação tributária."""
        self.company.l10n_br_esocial_class_trib_id = False
        s1000 = self.env["l10n_br.esocial.s1000"].create(
            {
                "operacao": "inclusao",
                "ini_valid": "2024-01",
                "company_id": self.company.id,
            }
        )
        with self.assertRaises(UserError):
            s1000._to_esociallib_dict()

    def test_s1000_gerar_xml(self):
        """Deve gerar XML via esociallib."""
        if not HAS_ESOCIALLIB:
            return
        s1000 = self.env["l10n_br.esocial.s1000"].create(
            {
                "operacao": "inclusao",
                "ini_valid": "2024-01",
                "company_id": self.company.id,
            }
        )
        xml = s1000._gerar_xml()
        self.assertIn("eSocial", xml)
        self.assertIn("evtInfoEmpregador", xml)


class TestS1020(TestESocialIntermediarioBase):
    """Testes do intermediário S-1020 (Tabela de Lotações)."""

    def test_s1020_dict_structure(self):
        """Dict do S-1020 deve conter campos obrigatórios."""
        # Empresa do Simples não recolhe terceiros (LC 123 art. 13, § 3º):
        # para exercitar um código de terceiros devido, sai do Simples.
        self.company.l10n_br_esocial_class_trib_id = self.env.ref(
            "l10n_br_esocial.class_trib_06"
        )
        s1020 = self.env["l10n_br.esocial.s1020"].create(
            {
                "operacao": "inclusao",
                "cod_lotacao": "LOT001",
                "ini_valid": "2024-01",
                "fpas": "515",
                "cod_tercs": "0115",
                "company_id": self.company.id,
            }
        )
        data = s1020._to_esociallib_dict()
        self.assertEqual(data["cod_lotacao"], "LOT001")
        self.assertEqual(data["fpas"], "515")
        self.assertEqual(data["cod_tercs"], "0115")
        self.assertIn("tp_lotacao", data)

    def test_s1020_requires_lotacao_tipo(self):
        """Deve dar erro se empresa não tem tipo lotação."""
        self.company.l10n_br_esocial_lotacao_id = False
        s1020 = self.env["l10n_br.esocial.s1020"].create(
            {
                "operacao": "inclusao",
                "cod_lotacao": "LOT001",
                "ini_valid": "2024-01",
                "company_id": self.company.id,
            }
        )
        with self.assertRaises(UserError):
            s1020._to_esociallib_dict()

    def test_s1020_gerar_xml(self):
        """Deve gerar XML via esociallib."""
        if not HAS_ESOCIALLIB:
            return
        # Empresa do Simples não recolhe terceiros (LC 123 art. 13, § 3º):
        # para exercitar um código de terceiros devido, sai do Simples.
        self.company.l10n_br_esocial_class_trib_id = self.env.ref(
            "l10n_br_esocial.class_trib_06"
        )
        s1020 = self.env["l10n_br.esocial.s1020"].create(
            {
                "operacao": "inclusao",
                "cod_lotacao": "LOT001",
                "ini_valid": "2024-01",
                "fpas": "515",
                "cod_tercs": "0115",
                "company_id": self.company.id,
            }
        )
        xml = s1020._gerar_xml()
        self.assertIn("eSocial", xml)
        self.assertIn("evtTabLotacao", xml)


class TestS2200(TestESocialIntermediarioBase):
    """Testes do intermediário S-2200 (Admissão)."""

    def test_s2200_dict_structure(self):
        """Dict do S-2200 deve conter dados do empregado."""
        s2200 = self.env["l10n_br.esocial.s2200"].create(
            {
                "employee_id": self.employee.id,
                "contract_id": self.contract.id,
                "company_id": self.company.id,
            }
        )
        data = s2200._to_esociallib_dict()
        self.assertEqual(data["cpf_trab"], "07616692941")
        self.assertEqual(data["nm_trab"], "Test eSocial Worker")
        self.assertEqual(data["sexo"], "M")
        self.assertEqual(data["matricula"], "MAT001")
        self.assertEqual(data["tp_reg_trab"], 1)
        self.assertEqual(data["vr_sal_fx"], "5000.0")
        self.assertEqual(data["dt_adm"], "2024-01-02")

    def test_s2200_requires_cpf(self):
        """Deve dar erro se empregado não tem CPF."""
        emp = self.env["hr.employee"].create(
            {
                "name": "No CPF",
                "l10n_br_esocial_matricula": "MAT099",
                "l10n_br_esocial_categoria_id": self.cat_101.id,
            }
        )
        s2200 = self.env["l10n_br.esocial.s2200"].create(
            {
                "employee_id": emp.id,
                "contract_id": self.contract.id,
                "company_id": self.company.id,
            }
        )
        with self.assertRaises(UserError):
            s2200._to_esociallib_dict()

    def test_s2200_requires_matricula(self):
        """Deve dar erro se empregado não tem matrícula."""
        emp = self.env["hr.employee"].create(
            {
                "name": "No Matricula",
                "cnpj_cpf": "857.642.960-52",
                "l10n_br_esocial_categoria_id": self.cat_101.id,
            }
        )
        s2200 = self.env["l10n_br.esocial.s2200"].create(
            {
                "employee_id": emp.id,
                "contract_id": self.contract.id,
                "company_id": self.company.id,
            }
        )
        with self.assertRaises(UserError):
            s2200._to_esociallib_dict()

    def test_s2200_gerar_xml(self):
        """Deve gerar XML via esociallib."""
        if not HAS_ESOCIALLIB:
            return
        s2200 = self.env["l10n_br.esocial.s2200"].create(
            {
                "employee_id": self.employee.id,
                "contract_id": self.contract.id,
                "company_id": self.company.id,
            }
        )
        xml = s2200._gerar_xml()
        self.assertIn("eSocial", xml)
        self.assertIn("evtAdmissao", xml)
        self.assertIn("07616692941", xml)


class TestS2206(TestESocialIntermediarioBase):
    """Testes do intermediário S-2206 (Alteração Contratual)."""

    def test_s2206_dict_structure(self):
        """Dict do S-2206 deve conter dados da alteração."""
        s2206 = self.env["l10n_br.esocial.s2206"].create(
            {
                "employee_id": self.employee.id,
                "contract_id": self.contract.id,
                "dt_alteracao": "2024-06-01",
                "dsc_alt": "Aumento salarial",
                "company_id": self.company.id,
            }
        )
        data = s2206._to_esociallib_dict()
        self.assertEqual(data["cpf_trab"], "07616692941")
        self.assertEqual(data["matricula"], "MAT001")
        self.assertEqual(data["dt_alteracao"], "2024-06-01")
        self.assertEqual(data["dsc_alt"], "Aumento salarial")
        self.assertEqual(data["vr_sal_fx"], "5000.0")

    def test_s2206_gerar_xml(self):
        """Deve gerar XML via esociallib."""
        if not HAS_ESOCIALLIB:
            return
        s2206 = self.env["l10n_br.esocial.s2206"].create(
            {
                "employee_id": self.employee.id,
                "contract_id": self.contract.id,
                "dt_alteracao": "2024-06-01",
                "company_id": self.company.id,
            }
        )
        xml = s2206._gerar_xml()
        self.assertIn("eSocial", xml)
        self.assertIn("evtAltContratual", xml)


class TestS2230(TestESocialIntermediarioBase):
    """Testes do intermediário S-2230 (Afastamento)."""

    def test_s2230_dict_inicio(self):
        """Dict do S-2230 com início de afastamento."""
        s2230 = self.env["l10n_br.esocial.s2230"].create(
            {
                "employee_id": self.employee.id,
                "dt_ini_afast": "2024-03-01",
                "cod_mot_afast": "01",
                "company_id": self.company.id,
            }
        )
        data = s2230._to_esociallib_dict()
        self.assertEqual(data["cpf_trab"], "07616692941")
        self.assertEqual(data["dt_ini_afast"], "2024-03-01")
        self.assertEqual(data["cod_mot_afast"], "01")

    def test_s2230_dict_termino(self):
        """Dict do S-2230 com término de afastamento."""
        s2230 = self.env["l10n_br.esocial.s2230"].create(
            {
                "employee_id": self.employee.id,
                "dt_term_afast": "2024-03-15",
                "company_id": self.company.id,
            }
        )
        data = s2230._to_esociallib_dict()
        self.assertEqual(data["dt_term_afast"], "2024-03-15")
        self.assertNotIn("dt_ini_afast", data)

    def test_s2230_requires_dates(self):
        """Deve dar erro se não tem data de início nem término."""
        s2230 = self.env["l10n_br.esocial.s2230"].create(
            {
                "employee_id": self.employee.id,
                "company_id": self.company.id,
            }
        )
        with self.assertRaises(UserError):
            s2230._to_esociallib_dict()

    def test_s2230_requires_motivo_for_inicio(self):
        """Deve dar erro se início sem motivo."""
        s2230 = self.env["l10n_br.esocial.s2230"].create(
            {
                "employee_id": self.employee.id,
                "dt_ini_afast": "2024-03-01",
                "company_id": self.company.id,
            }
        )
        with self.assertRaises(UserError):
            s2230._to_esociallib_dict()

    def test_s2230_motivo_from_m2o(self):
        """Deve usar código do M2O motivo se cod_mot_afast vazio."""
        s2230 = self.env["l10n_br.esocial.s2230"].create(
            {
                "employee_id": self.employee.id,
                "dt_ini_afast": "2024-03-01",
                "motivo_afastamento_id": self.mot_afast_01.id,
                "company_id": self.company.id,
            }
        )
        data = s2230._to_esociallib_dict()
        self.assertEqual(data["cod_mot_afast"], "01")

    def test_s2230_gerar_xml(self):
        """Deve gerar XML via esociallib."""
        if not HAS_ESOCIALLIB:
            return
        s2230 = self.env["l10n_br.esocial.s2230"].create(
            {
                "employee_id": self.employee.id,
                "dt_ini_afast": "2024-03-01",
                "cod_mot_afast": "01",
                "company_id": self.company.id,
            }
        )
        xml = s2230._gerar_xml()
        self.assertIn("eSocial", xml)
        self.assertIn("evtAfastTemp", xml)


class TestS2230Devido(TestESocialIntermediarioBase):
    """S-2230 de doença só é devido acima de 15 dias (MOS), com recaída."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.tipo_doenca = cls.env["hr.leave.type"].create(
            {
                "name": "Doença T104",
                "requires_allocation": "no",
                "leave_validation_type": "no_validation",
                "l10n_br_afastamento_inss": True,
            }
        )
        cls.mot_afast_03 = cls.env.ref("l10n_br_esocial.mot_afast_03")
        cls.mot_afast_16 = cls.env.ref("l10n_br_esocial.mot_afast_16")

    def _licenca(self, inicio, fim, tipo=None):
        leave = self.env["hr.leave"].create(
            {
                "employee_id": self.employee.id,
                "holiday_status_id": (tipo or self.tipo_doenca).id,
                "request_date_from": inicio,
                "request_date_to": fim,
            }
        )
        if leave.state != "validate":
            leave.sudo().action_validate()
        return leave

    def _s2230(self, inicio, fim, motivo=None):
        return self.env["l10n_br.esocial.s2230"].create(
            {
                "employee_id": self.employee.id,
                "dt_ini_afast": inicio,
                "dt_term_afast": fim,
                "motivo_afastamento_id": (motivo or self.mot_afast_03).id,
                "company_id": self.company.id,
            }
        )

    def _gera(self, inicio, fim, motivo=None):
        self._licenca(inicio, fim)
        return self._s2230(inicio, fim, motivo)._to_esociallib_dict()

    def test_doenca_ate_15_dias_nao_gera(self):
        """15 dias exatos: a empresa paga tudo, sem S-2230."""
        self._licenca("2024-03-01", "2024-03-15")
        with self.assertRaises(UserError):
            self._s2230("2024-03-01", "2024-03-15")._to_esociallib_dict()

    def test_doenca_curta_de_tres_dias_nao_gera(self):
        self._licenca("2024-03-01", "2024-03-03")
        with self.assertRaises(UserError):
            self._s2230("2024-03-01", "2024-03-03")._to_esociallib_dict()

    def test_doenca_16_dias_gera(self):
        data = self._gera("2024-03-01", "2024-03-16")
        self.assertEqual(data["dt_ini_afast"], "2024-03-01")
        self.assertEqual(data["dt_term_afast"], "2024-03-16")

    def test_doenca_acidente_do_trabalho_segue_a_mesma_regra(self):
        self._licenca("2024-03-01", "2024-03-10")
        with self.assertRaises(UserError):
            self._s2230(
                "2024-03-01", "2024-03-10", self.mot_afast_01
            )._to_esociallib_dict()

    def test_recaida_dois_de_10_dias_em_60_dias_gera_o_segundo(self):
        """10 + 10 dias com 30 de intervalo: o segundo passa de 15 somado."""
        self._licenca("2024-03-01", "2024-03-10")
        with self.assertRaises(UserError):
            self._s2230("2024-03-01", "2024-03-10")._to_esociallib_dict()
        self._licenca("2024-04-09", "2024-04-18")
        data = self._s2230("2024-04-09", "2024-04-18")._to_esociallib_dict()
        self.assertEqual(data["dt_ini_afast"], "2024-04-09")

    def test_recaida_intervalo_de_60_dias_soma(self):
        self._licenca("2024-03-01", "2024-03-10")
        self._licenca("2024-05-09", "2024-05-18")  # 60 dias após o fim do 1º
        data = self._s2230("2024-05-09", "2024-05-18")._to_esociallib_dict()
        self.assertEqual(data["dt_ini_afast"], "2024-05-09")

    def test_intervalo_de_61_dias_nao_soma(self):
        self._licenca("2024-03-01", "2024-03-10")
        self._licenca("2024-05-10", "2024-05-19")  # 61 dias após o fim do 1º
        with self.assertRaises(UserError):
            self._s2230("2024-05-10", "2024-05-19")._to_esociallib_dict()

    def test_termino_de_inicio_nao_gerado_e_recusado(self):
        """Não gera o término de um afastamento cujo início não é devido."""
        self._licenca("2024-03-01", "2024-03-10")
        termino = self.env["l10n_br.esocial.s2230"].create(
            {
                "employee_id": self.employee.id,
                "dt_term_afast": "2024-03-10",
                "company_id": self.company.id,
            }
        )
        with self.assertRaises(UserError):
            termino._to_esociallib_dict()

    def test_termino_de_afastamento_longo_segue(self):
        self._licenca("2024-03-01", "2024-03-20")
        termino = self.env["l10n_br.esocial.s2230"].create(
            {
                "employee_id": self.employee.id,
                "dt_term_afast": "2024-03-20",
                "company_id": self.company.id,
            }
        )
        self.assertEqual(termino._to_esociallib_dict()["dt_term_afast"], "2024-03-20")

    def test_outros_motivos_nao_tem_limite_de_15_dias(self):
        """Licença remunerada (16) de 3 dias continua gerando o S-2230."""
        data = self._s2230("2024-03-01", "2024-03-03", self.mot_afast_16)
        self.assertEqual(data._to_esociallib_dict()["cod_mot_afast"], "16")


class TestS2299(TestESocialIntermediarioBase):
    """Testes do intermediário S-2299 (Desligamento)."""

    def test_s2299_dict_structure(self):
        """Dict do S-2299 deve conter dados do desligamento."""
        s2299 = self.env["l10n_br.esocial.s2299"].create(
            {
                "employee_id": self.employee.id,
                "contract_id": self.contract.id,
                "dt_deslig": "2024-12-31",
                "motivo_desligamento_id": self.mot_deslig_02.id,
                "company_id": self.company.id,
            }
        )
        data = s2299._to_esociallib_dict()
        self.assertEqual(data["cpf_trab"], "07616692941")
        self.assertEqual(data["matricula"], "MAT001")
        self.assertEqual(data["dt_deslig"], "2024-12-31")
        self.assertEqual(data["mtv_deslig"], "02")
        self.assertEqual(data["ind_pagto_api"], "N")

    def test_s2299_with_aviso_previo(self):
        """Dict do S-2299 com aviso prévio indenizado."""
        s2299 = self.env["l10n_br.esocial.s2299"].create(
            {
                "employee_id": self.employee.id,
                "contract_id": self.contract.id,
                "dt_deslig": "2024-12-31",
                "motivo_desligamento_id": self.mot_deslig_02.id,
                "ind_pagto_api": "S",
                "dt_proj_fim_api": "2025-01-30",
                "company_id": self.company.id,
            }
        )
        data = s2299._to_esociallib_dict()
        self.assertEqual(data["ind_pagto_api"], "S")
        self.assertEqual(data["dt_proj_fim_api"], "2025-01-30")

    def test_s2299_gerar_xml(self):
        """Deve gerar XML via esociallib."""
        if not HAS_ESOCIALLIB:
            return
        s2299 = self.env["l10n_br.esocial.s2299"].create(
            {
                "employee_id": self.employee.id,
                "contract_id": self.contract.id,
                "dt_deslig": "2024-12-31",
                "motivo_desligamento_id": self.mot_deslig_02.id,
                "company_id": self.company.id,
            }
        )
        xml = s2299._gerar_xml()
        self.assertIn("eSocial", xml)
        self.assertIn("evtDeslig", xml)
