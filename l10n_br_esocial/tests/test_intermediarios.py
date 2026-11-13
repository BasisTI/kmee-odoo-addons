# Copyright 2024 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import logging
from datetime import date
from unittest.mock import patch

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
    """S-2230 conforme o MOS S-1.3: motivo 01 sempre; motivo 03 com limite e recaída."""

    MSG = "não é de informação obrigatória"

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

    def _licenca(self, inicio, fim):
        leave = self.env["hr.leave"].create(
            {
                "employee_id": self.employee.id,
                "holiday_status_id": self.tipo_doenca.id,
                "request_date_from": inicio,
                "request_date_to": fim,
            }
        )
        if leave.state != "validate":
            leave.sudo().action_validate()
        return leave

    def _s2230(self, inicio, fim, motivo=None, **extra):
        valores = {
            "employee_id": self.employee.id,
            "dt_ini_afast": inicio,
            "dt_term_afast": fim,
            "company_id": self.company.id,
        }
        if inicio:
            valores["motivo_afastamento_id"] = (motivo or self.mot_afast_03).id
        valores.update(extra)
        return self.env["l10n_br.esocial.s2230"].create(valores)

    def _gera(self, inicio, fim, motivo=None, **extra):
        return self._s2230(inicio, fim, motivo, **extra)._to_esociallib_dict()

    def _recusa(self, inicio, fim, motivo=None, **extra):
        with self.assertRaisesRegex(UserError, self.MSG):
            self._gera(inicio, fim, motivo, **extra)

    # Motivo 03: limite de 15 dias
    def test_doenca_ate_15_dias_nao_gera(self):
        self._licenca("2024-03-01", "2024-03-15")
        self._recusa("2024-03-01", "2024-03-15")

    def test_doenca_curta_de_tres_dias_nao_gera(self):
        self._licenca("2024-03-01", "2024-03-03")
        self._recusa("2024-03-01", "2024-03-03")

    def test_doenca_16_dias_gera(self):
        self._licenca("2024-03-01", "2024-03-16")
        data = self._gera("2024-03-01", "2024-03-16")
        self.assertEqual(data["dt_ini_afast"], "2024-03-01")
        self.assertEqual(data["dt_term_afast"], "2024-03-16")

    def test_doenca_curta_opcional_gera_quando_pedido(self):
        self._licenca("2024-03-01", "2024-03-03")
        data = self._gera("2024-03-01", "2024-03-03", informar_opcional=True)
        self.assertEqual(data["cod_mot_afast"], "03")

    def test_outros_motivos_nao_tem_limite_de_15_dias(self):
        data = self._gera("2024-03-01", "2024-03-03", self.mot_afast_16)
        self.assertEqual(data["cod_mot_afast"], "16")

    # Motivo 01: desde o 1º dia
    def test_acidente_do_trabalho_de_1_dia_gera(self):
        self._licenca("2024-03-01", "2024-03-01")
        data = self._gera("2024-03-01", "2024-03-01", self.mot_afast_01)
        self.assertEqual(data["cod_mot_afast"], "01")

    def test_acidente_do_trabalho_termino_curto_gera(self):
        self._licenca("2024-03-01", "2024-03-10")
        self._s2230("2024-03-01", None, self.mot_afast_01)
        termino = self._s2230(None, "2024-03-10")
        self.assertEqual(termino._to_esociallib_dict()["dt_term_afast"], "2024-03-10")

    # Recaída
    def test_recaida_dois_de_10_dias_informa_os_dois(self):
        self._licenca("2024-03-01", "2024-03-10")
        self._licenca("2024-04-09", "2024-04-18")
        self.assertEqual(
            self._gera("2024-03-01", "2024-03-10")["dt_ini_afast"], "2024-03-01"
        )
        self.assertEqual(
            self._gera("2024-04-09", "2024-04-18")["dt_ini_afast"], "2024-04-09"
        )

    def test_recaida_exemplo_do_mos_3_10_3(self):
        self._licenca("2024-03-01", "2024-03-03")
        self._licenca("2024-03-20", "2024-03-29")
        self._licenca("2024-04-20", "2024-04-22")
        for ini, fim in (
            ("2024-03-01", "2024-03-03"),
            ("2024-03-20", "2024-03-29"),
            ("2024-04-20", "2024-04-22"),
        ):
            self.assertEqual(self._gera(ini, fim)["dt_ini_afast"], ini)

    def test_recaida_intervalo_de_60_dias_soma(self):
        self._licenca("2024-03-01", "2024-03-10")
        self._licenca("2024-05-09", "2024-05-18")  # 60 dias após o fim do 1º
        self.assertEqual(
            self._gera("2024-05-09", "2024-05-18")["dt_ini_afast"], "2024-05-09"
        )

    def test_intervalo_de_61_dias_nao_soma(self):
        self._licenca("2024-03-01", "2024-03-10")
        self._licenca("2024-05-10", "2024-05-19")  # 61 dias após o fim do 1º
        self._recusa("2024-05-10", "2024-05-19")

    def test_janela_conta_do_termino_do_primeiro(self):
        """O 3º começa a 63 dias do fim do 1º, ainda que a 29 do fim do 2º."""
        self._licenca("2024-03-01", "2024-03-05")
        self._licenca("2024-03-30", "2024-04-08")
        self._licenca("2024-05-07", "2024-05-12")
        self._recusa("2024-05-07", "2024-05-12")

    def test_retorno_de_afastamento_acima_de_15_dias_torna_devido(self):
        self._licenca("2024-03-01", "2024-03-05")
        self._licenca("2024-03-30", "2024-04-30")
        self._licenca("2024-06-20", "2024-06-22")
        self.assertEqual(
            self._gera("2024-06-20", "2024-06-22")["dt_ini_afast"], "2024-06-20"
        )

    def test_acidente_do_trabalho_nao_soma_com_doenca(self):
        self._licenca("2024-03-01", "2024-03-10")
        self._s2230("2024-03-01", "2024-03-10", self.mot_afast_01)
        self._licenca("2024-03-20", "2024-03-29")
        self._recusa("2024-03-20", "2024-03-29")

    def test_recaida_sem_evento_avisa_e_gera_pendente(self):
        self._licenca("2024-03-01", "2024-03-10")
        self._licenca("2024-04-09", "2024-04-18")
        segundo = self._s2230("2024-04-09", "2024-04-18")
        self.assertEqual(
            segundo._recaida_sem_evento(), [(date(2024, 3, 1), date(2024, 3, 10))]
        )
        criado = segundo.action_gerar_recaida_pendente()
        self.assertEqual(criado.dt_ini_afast, date(2024, 3, 1))
        self.assertEqual(criado._to_esociallib_dict()["dt_term_afast"], "2024-03-10")
        self.assertFalse(segundo._recaida_sem_evento())

    # Início em aberto e término
    def test_inicio_em_aberto_de_doenca_curta_e_recusado(self):
        self._licenca("2024-03-01", "2024-03-05")
        self._recusa("2024-03-01", None)

    def test_inicio_em_aberto_sem_afastamento_registrado_segue(self):
        data = self._gera("2024-03-01", None, self.mot_afast_01)
        self.assertNotIn("dt_term_afast", data)

    def test_termino_de_inicio_nao_gerado_e_recusado(self):
        self._licenca("2024-03-01", "2024-03-10")
        self._recusa(None, "2024-03-10")

    def test_termino_de_inicio_gerado_segue_mesmo_curto(self):
        """Início opcional já enviado: o término vai, para não deixar aberto."""
        self._licenca("2024-03-01", "2024-03-05")
        self._s2230("2024-03-01", None, informar_opcional=True)
        self.assertEqual(self._gera(None, "2024-03-05")["dt_term_afast"], "2024-03-05")

    def test_termino_de_afastamento_longo_segue(self):
        self._licenca("2024-03-01", "2024-03-20")
        self.assertEqual(self._gera(None, "2024-03-20")["dt_term_afast"], "2024-03-20")

    # infoMesmoMtv (leiaute S-1.3, a partir de 2026-10-26), motivos 01 e 03
    MSG_INFO = "Mesmo motivo do afastamento anterior"

    def _recusa_info(self, *args, **kwargs):
        with self.assertRaisesRegex(UserError, self.MSG_INFO):
            self._gera(*args, **kwargs)

    def _recaida(self):
        """Dois afastamentos de 20 dias, o 2º a 10 dias do término do 1º."""
        self._licenca("2026-11-01", "2026-11-20")
        self._licenca("2026-11-30", "2026-12-19")

    def test_recaida_sem_informar_e_recusada(self):
        self._recaida()
        self._recusa_info("2026-11-30", "2026-12-19")

    def test_recaida_informada_vai_no_evento(self):
        self._recaida()
        for valor in ("S", "N"):
            data = self._gera("2026-11-30", "2026-12-19", info_mesmo_mtv=valor)
            self.assertEqual(data["info_mesmo_mtv"], valor)

    def test_primeiro_afastamento_nao_leva_o_campo(self):
        self._recaida()
        self.assertNotIn("info_mesmo_mtv", self._gera("2026-11-01", "2026-11-20"))

    def test_anterior_a_mais_de_60_dias_nao_exige(self):
        self._licenca("2026-11-01", "2026-11-20")
        self._licenca("2027-01-20", "2027-02-10")  # 61 dias após o término
        self.assertNotIn("info_mesmo_mtv", self._gera("2027-01-20", "2027-02-10"))

    def test_anterior_a_60_dias_exige(self):
        self._licenca("2026-11-01", "2026-11-20")
        self._licenca("2027-01-19", "2027-02-10")  # 60 dias após o término
        self._recusa_info("2027-01-19", "2027-02-10")

    def test_inicio_antes_de_26_10_2026_nao_leva_o_campo(self):
        self._licenca("2026-09-01", "2026-09-20")
        self._licenca("2026-10-10", "2026-10-25")
        data = self._gera("2026-10-10", "2026-10-25", info_mesmo_mtv="S")
        self.assertNotIn("info_mesmo_mtv", data)

    def test_inicio_em_26_10_2026_ja_exige(self):
        self._licenca("2026-10-01", "2026-10-20")
        self._licenca("2026-10-26", "2026-11-15")
        self._recusa_info("2026-10-26", "2026-11-15")

    def test_outros_motivos_nao_levam_o_campo(self):
        self._recaida()
        data = self._gera(
            "2026-11-30", "2026-12-19", self.mot_afast_16, info_mesmo_mtv="S"
        )
        self.assertNotIn("info_mesmo_mtv", data)

    def test_acidente_do_trabalho_com_anterior_exige(self):
        self._s2230("2026-11-01", "2026-11-03", self.mot_afast_01)
        self._recusa_info("2026-11-20", "2026-11-22", self.mot_afast_01)
        data = self._gera(
            "2026-11-20", "2026-11-22", self.mot_afast_01, info_mesmo_mtv="N"
        )
        self.assertEqual(data["info_mesmo_mtv"], "N")

    def test_acidente_do_trabalho_nao_conta_doenca_anterior(self):
        self._licenca("2026-11-01", "2026-11-20")
        data = self._gera("2026-11-30", "2026-12-02", self.mot_afast_01)
        self.assertNotIn("info_mesmo_mtv", data)

    def test_termino_nao_leva_o_campo(self):
        self._recaida()
        self.assertNotIn("info_mesmo_mtv", self._gera(None, "2026-12-19"))

    def test_xml_traz_o_info_mesmo_mtv_apos_o_motivo(self):
        if not HAS_ESOCIALLIB:
            return
        self._recaida()
        xml = self._s2230("2026-11-30", "2026-12-19", info_mesmo_mtv="S")._gerar_xml()
        self.assertRegex(
            xml, r"<codMotAfast>03</codMotAfast>\s*<infoMesmoMtv>S</infoMesmoMtv>"
        )

    def test_acidente_com_termino_em_registro_separado_fecha_o_anterior(self):
        """Fluxo do CAT: início num S-2230, término noutro, sem prazo em aberto."""
        self._s2230("2026-11-01", None, self.mot_afast_01)
        self._s2230(None, "2026-11-05")
        # 60 dias após o término (05/11) exige; 61 não.
        self._recusa_info("2027-01-04", "2027-01-06", self.mot_afast_01)

    def test_acidente_a_61_dias_do_termino_em_registro_separado_nao_exige(self):
        self._s2230("2026-11-01", None, self.mot_afast_01)
        self._s2230(None, "2026-11-05")
        data = self._gera("2027-01-05", "2027-01-07", self.mot_afast_01)
        self.assertNotIn("info_mesmo_mtv", data)

    def test_acidente_meses_depois_do_termino_em_registro_separado_nao_exige(self):
        self._s2230("2026-11-01", None, self.mot_afast_01)
        self._s2230(None, "2026-11-05")
        data = self._gera("2027-08-01", "2027-08-03", self.mot_afast_01)
        self.assertNotIn("info_mesmo_mtv", data)

    def test_acidente_com_termino_pelo_afastamento_registrado(self):
        """CAT grava o último dia trabalhado; o afastamento começa no dia seguinte."""
        self._s2230("2026-11-01", None, self.mot_afast_01)
        self._licenca("2026-11-02", "2026-11-05")
        data = self._gera("2027-08-01", "2027-08-03", self.mot_afast_01)
        self.assertNotIn("info_mesmo_mtv", data)
        self._recusa_info("2027-01-04", "2027-01-06", self.mot_afast_01)

    def test_acidente_sem_nenhum_termino_segue_em_aberto(self):
        self._s2230("2026-11-01", None, self.mot_afast_01)
        self._recusa_info("2027-08-01", "2027-08-03", self.mot_afast_01)

    def test_s_sem_anterior_nao_vai_e_n_vai(self):
        self._licenca("2026-11-01", "2026-11-20")
        data = self._gera("2026-11-01", "2026-11-20", info_mesmo_mtv="S")
        self.assertNotIn("info_mesmo_mtv", data)
        data = self._gera("2026-11-01", "2026-11-20", info_mesmo_mtv="N")
        self.assertEqual(data["info_mesmo_mtv"], "N")

    def test_conta_por_contrato(self):
        self._licenca("2026-11-01", "2026-11-20")
        self.contract.write({"date_end": "2026-11-25", "state": "close"})
        self.env["hr.contract"].create(
            {
                "name": "Novo contrato",
                "employee_id": self.employee.id,
                "wage": 3000.0,
                "date_start": "2026-12-01",
                "state": "open",
            }
        )
        self._licenca("2026-12-10", "2026-12-30")
        data = self._gera("2026-12-10", "2026-12-30")
        self.assertNotIn("info_mesmo_mtv", data)

    def test_acidente_nao_e_anterior_de_doenca_e_vice_versa(self):
        # Acidente com último dia trabalhado em 31/10 e afastamento de 01 a 10/11.
        self._licenca("2026-11-01", "2026-11-10")
        self._s2230("2026-10-31", "2026-11-10", self.mot_afast_01)
        self._licenca("2026-11-20", "2026-12-10")
        data = self._gera("2026-11-20", "2026-12-10")
        self.assertNotIn("info_mesmo_mtv", data)
        # E a doença anterior não é anterior do acidente.
        self._s2230("2026-12-20", "2026-12-22", self.mot_afast_03, info_mesmo_mtv="N")
        data = self._gera("2027-02-15", "2027-02-16", self.mot_afast_01)
        self.assertNotIn("info_mesmo_mtv", data)

    def test_anterior_curto_da_cadeia_exige_mesmo_sem_s2230(self):
        """3 dias + 23 dias é recaída (soma acima de 15): o anterior é devido."""
        self._licenca("2026-11-01", "2026-11-03")
        self._licenca("2026-12-01", "2026-12-23")
        self._recusa_info("2026-12-01", "2026-12-23")

    def test_anterior_curto_fora_de_cadeia_nao_conta(self):
        """3 dias opcionais, sem S-2230, a mais de 60 dias do seguinte."""
        self._licenca("2026-11-01", "2026-11-03")
        self._licenca("2027-02-01", "2027-02-23")
        data = self._gera("2027-02-01", "2027-02-23")
        self.assertNotIn("info_mesmo_mtv", data)

    def test_anterior_curto_com_s2230_exige(self):
        self._licenca("2026-11-01", "2026-11-03")
        self._s2230("2026-11-01", "2026-11-03", informar_opcional=True)
        self._licenca("2026-12-01", "2026-12-23")
        self._recusa_info("2026-12-01", "2026-12-23")

    def test_pendentes_da_recaida_pedem_o_s_n_na_acao(self):
        self._licenca("2026-11-01", "2026-11-10")
        self._licenca("2026-11-20", "2026-11-29")
        self._licenca("2026-12-10", "2026-12-19")
        ultimo = self._s2230("2026-12-10", "2026-12-19", info_mesmo_mtv="S")
        criados = ultimo.action_gerar_recaida_pendente(info_mesmo_mtv="N")
        self.assertEqual(
            sorted(criados.mapped("dt_ini_afast")),
            [date(2026, 11, 1), date(2026, 11, 20)],
        )
        segundo = criados.filtered(lambda r: r.dt_ini_afast == date(2026, 11, 20))
        self.assertEqual(segundo._to_esociallib_dict()["info_mesmo_mtv"], "N")

    def test_acao_de_pendentes_sem_s_n_recusa(self):
        self._licenca("2026-11-01", "2026-11-10")
        self._licenca("2026-11-20", "2026-11-29")
        self._licenca("2026-12-10", "2026-12-19")
        ultimo = self._s2230("2026-12-10", "2026-12-19", info_mesmo_mtv="S")
        with self.assertRaisesRegex(UserError, "info_mesmo_mtv='S' ou 'N'"):
            ultimo.action_gerar_recaida_pendente()


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

    def _s2299_rescisao(self, **extra):
        slip = self.env["hr.payslip"].create(
            {
                "name": "Rescisão",
                "employee_id": self.employee.id,
                "contract_id": self.contract.id,
                "date_from": "2024-12-01",
                "date_to": "2024-12-31",
            }
        )
        vals = {
            "employee_id": self.employee.id,
            "contract_id": self.contract.id,
            "dt_deslig": "2024-12-31",
            "motivo_desligamento_id": self.mot_deslig_02.id,
            "company_id": self.company.id,
            "payslip_id": slip.id,
        }
        vals.update(extra)
        return self.env["l10n_br.esocial.s2299"].create(vals)

    def _com_aviso_da_folha(self, indenizado):
        """Simula o módulo de rescisão (``l10n_br_hr_vacation``) no holerite."""
        classe = self.env.registry["hr.payslip"]
        return patch.multiple(
            classe,
            create=True,
            _l10n_br_aviso_indenizado_devido=lambda slip: indenizado,
            _l10n_br_dias_aviso_previo=lambda slip: 33,
        )

    def test_s2299_aviso_indenizado_vem_do_holerite_de_rescisao(self):
        """TG-106: o indPagtoAPI segue a verba de aviso da rescisão, não o padrão N."""
        s2299 = self._s2299_rescisao()
        with self._com_aviso_da_folha(True):
            data = s2299._to_esociallib_dict()
        self.assertEqual(data["ind_pagto_api"], "S")
        # desligamento 2024-12-31 + 33 dias de aviso (Lei 12.506/2011)
        self.assertEqual(data["dt_proj_fim_api"], "2025-02-02")

    def test_s2299_aviso_nao_indenizado_no_holerite_prevalece_sobre_o_campo(self):
        s2299 = self._s2299_rescisao(ind_pagto_api="S", dt_proj_fim_api="2025-01-30")
        with self._com_aviso_da_folha(False):
            data = s2299._to_esociallib_dict()
        self.assertEqual(data["ind_pagto_api"], "N")
        self.assertNotIn("dt_proj_fim_api", data)

    def test_s2299_aviso_indenizado_exige_data_projetada(self):
        s2299 = self._s2299_rescisao(payslip_id=False, ind_pagto_api="S")
        with self.assertRaisesRegex(UserError, "Data Projetada"):
            s2299._to_esociallib_dict()

    def test_s2299_data_projetada_nao_pode_ser_anterior_ao_desligamento(self):
        s2299 = self._s2299_rescisao(
            payslip_id=False, ind_pagto_api="S", dt_proj_fim_api="2024-12-30"
        )
        with self.assertRaisesRegex(UserError, "anterior ao desligamento"):
            s2299._to_esociallib_dict()

    def test_s2299_gerado_a_partir_do_holerite_de_rescisao_liga_o_holerite(self):
        """TG-106: a ação do holerite cria o S-2299 com ``payslip_id`` e o aviso."""
        if not HAS_ESOCIALLIB:
            self.skipTest("esociallib não instalada")
        slip = self.env["hr.payslip"].create(
            {
                "name": "Rescisão",
                "employee_id": self.employee.id,
                "contract_id": self.contract.id,
                "date_from": "2024-12-01",
                "date_to": "2024-12-31",
                "state": "done",
                "struct_id": self.env["hr.payroll.structure"]
                .create({"name": "Rescisão", "code": "RESCISAO"})
                .id,
            }
        )
        with self.assertRaisesRegex(UserError, "Motivo Desligamento"):
            slip.action_esocial_gerar_s2299()
        self.contract.l10n_br_esocial_motivo_deslig_id = self.mot_deslig_02
        with self._com_aviso_da_folha(True):
            slip.action_esocial_gerar_s2299()
        s2299 = self.env["l10n_br.esocial.s2299"].search([("payslip_id", "=", slip.id)])
        self.assertEqual(len(s2299), 1)
        self.assertEqual(str(s2299.dt_deslig), "2024-12-31")
        self.assertIn("<indPagtoAPI>S</indPagtoAPI>", s2299.evento_id.xml_envio)
        self.assertIn(
            "<dtProjFimAPI>2025-02-02</dtProjFimAPI>", s2299.evento_id.xml_envio
        )

    def _regra_rubrica(self, code, cod_rubr=None):
        categoria = self.env["hr.salary.rule.category"].search(
            [("code", "=", "ALW")], limit=1
        ) or self.env["hr.salary.rule.category"].create(
            {"name": "Provento", "code": "ALW"}
        )
        vals = {"name": code, "code": code, "category_id": categoria.id}
        if cod_rubr:
            vals.update(
                {
                    "l10n_br_esocial_cod_rubr": cod_rubr,
                    "l10n_br_esocial_ide_tab_rubr": "1",
                    "l10n_br_esocial_nat_rubr_id": self.env.ref(
                        "l10n_br_esocial.nat_rubr_1000"
                    ).id,
                    "l10n_br_esocial_tp_rubr": "1",
                }
            )
        return self.env["hr.salary.rule"].create(vals)

    def _linha_rescisao(self, slip, regra, valor):
        self.env["hr.payslip.line"].create(
            {
                "slip_id": slip.id,
                "salary_rule_id": regra.id,
                "name": regra.code,
                "code": regra.code,
                "employee_id": self.employee.id,
                "contract_id": self.contract.id,
                "quantity": 1,
                "amount": valor,
                "rate": 100,
            }
        )

    def test_s2299_verbas_rescisorias_levam_aviso_indenizado_e_reflexos(self):
        """TG-103: o aviso indenizado e os reflexos saem em verbasResc/detVerbas."""
        s2299 = self._s2299_rescisao()
        slip = s2299.payslip_id
        self._linha_rescisao(slip, self._regra_rubrica("AVISO_X", "AVISO"), 3300.0)
        self._linha_rescisao(slip, self._regra_rubrica("FERIAS_X", "FERIAS"), 1100.0)
        self._linha_rescisao(slip, self._regra_rubrica("ZERADA_X", "ZERO"), 0.0)
        self._linha_rescisao(slip, self._regra_rubrica("SEM_CONFIG_X"), 50.0)
        with self._com_aviso_da_folha(True), mute_logger(
            "odoo.addons.l10n_br_esocial.models.intermediarios.s2299_desligamento"
        ):
            data = s2299._to_esociallib_dict()
        self.assertEqual(data["ind_pagto_api"], "S")
        self.assertEqual(data["dt_proj_fim_api"], "2025-02-02")
        (dm,) = data["verbas_resc"]
        self.assertEqual(dm["ide_dm_dev"], s2299.get_ide_dm_dev())
        (estab,) = dm["info_per_apur"]["ide_estab_lot"]
        self.assertEqual(
            [(d["cod_rubr"], d["vr_rubr"]) for d in estab["det_verbas"]],
            [("AVISO", "3300.0"), ("FERIAS", "1100.0")],
        )
        self.assertIn("SEM_CONFIG_X", s2299.avisos)

    def test_s2299_sem_holerite_nao_leva_verbas_rescisorias(self):
        s2299 = self._s2299_rescisao(payslip_id=False)
        self.assertNotIn("verbas_resc", s2299._to_esociallib_dict())

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
