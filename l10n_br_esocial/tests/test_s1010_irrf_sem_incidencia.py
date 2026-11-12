# Copyright 2026 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""TG-125: regra sem incidência de IRRF no S-1010 (Tabela 21)."""

import importlib.util

from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase
from odoo.tools import file_path


class TestS1010IrrfSemIncidencia(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.rule = cls.env["hr.salary.rule"].search([], limit=1)
        cls.rule.write(
            {
                "l10n_br_esocial_cod_rubr": "DESC_CONVENIO",
                "l10n_br_esocial_ide_tab_rubr": "1",
                "l10n_br_esocial_nat_rubr_id": cls.env.ref(
                    "l10n_br_esocial.nat_rubr_1000"
                ).id,
                "l10n_br_esocial_tp_rubr": "2",
                "l10n_br_esocial_cod_inc_cp": "00",
                "l10n_br_esocial_cod_inc_fgts": "00",
                "l10n_br_esocial_cod_inc_irrf": False,
            }
        )
        cls.company = cls.env.company
        if not cls.company.partner_id.vat:
            cls.company.partner_id.write({"vat": "02.546.716/0001-46"})

    def _s1010(self):
        return self.env["l10n_br.esocial.s1010"].create(
            {
                "salary_rule_id": self.rule.id,
                "operacao": "inclusao",
                "ini_valid": "2024-01",
                "company_id": self.company.id,
            }
        )

    def _grava_codigo_legado(self, codigo):
        """Como a regra ficou no banco antes da TG-107: valor fora da lista."""
        self.env.cr.execute(
            "UPDATE hr_salary_rule SET l10n_br_esocial_cod_inc_irrf = %s WHERE id = %s",
            (codigo, self.rule.id),
        )
        self.rule.invalidate_recordset()

    def test_sem_incidencia_sai_com_codigo_vigente(self):
        """Campo vazio emitia 0 (expirado em 30/06/2021); agora sai o 09."""
        dados = self._s1010()._to_esociallib_dict()
        self.assertEqual(dados["cod_inc_irrf"], 9)

    def test_codigo_escolhido_e_mantido(self):
        self.rule.l10n_br_esocial_cod_inc_irrf = "11"
        self.assertEqual(self._s1010()._to_esociallib_dict()["cod_inc_irrf"], 11)

    def test_codigo_expirado_recusa_a_geracao(self):
        self._grava_codigo_legado("00")
        with self.assertRaisesRegex(UserError, "expirou na Tabela 21"):
            self._s1010()._to_esociallib_dict()

    def test_regra_com_codigo_expirado_e_sinalizada(self):
        Regra = self.env["hr.salary.rule"]
        self.assertFalse(self.rule.l10n_br_esocial_cod_inc_irrf_expirado)
        self._grava_codigo_legado("00")
        self.assertTrue(self.rule.l10n_br_esocial_cod_inc_irrf_expirado)
        self.assertIn(
            self.rule, Regra.search([("l10n_br_esocial_cod_inc_irrf_expirado", "=", 1)])
        )
        self.assertNotIn(
            self.rule,
            Regra.search([("l10n_br_esocial_cod_inc_irrf_expirado", "!=", 1)]),
        )

    def test_vazio_e_09_sao_a_mesma_definicao_de_rubrica(self):
        sem = self.rule._esocial_definicao_rubrica()
        self.rule.l10n_br_esocial_cod_inc_irrf = "09"
        self.assertEqual(self.rule._esocial_definicao_rubrica(), sem)

    def test_aviso_na_tela_da_regra(self):
        view = self.env.ref("l10n_br_esocial.view_hr_salary_rule_form_esocial")
        self.assertIn("l10n_br_esocial_cod_inc_irrf_expirado", view.arch)

    def test_migracao_avisa_de_codigo_expirado_e_de_rotulo_trocado(self):
        caminho = file_path("l10n_br_esocial/migrations/18.0.1.5.0/post-migration.py")
        spec = importlib.util.spec_from_file_location("migracao_tg125_aviso", caminho)
        migracao = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(migracao)
        self._grava_codigo_legado("00")
        with self.assertLogs(migracao.__name__, level="WARNING") as log:
            migracao.migrate(self.env.cr, "18.0.1.4.0")
        self.assertTrue(any("expirada" in linha for linha in log.output))
        self._grava_codigo_legado("52")
        with self.assertLogs(migracao.__name__, level="WARNING") as log:
            migracao.migrate(self.env.cr, "18.0.1.4.0")
        self.assertTrue(any("rótulo" in linha for linha in log.output))


class TestS1010IrrfVencimento(TestS1010IrrfSemIncidencia):
    """TG-131: vencimento (tpRubr 1) sem incidência de IRRF exige escolha."""

    def _tipo(self, tipo):
        self.rule.l10n_br_esocial_tp_rubr = tipo

    def test_vencimento_sem_incidencia_recusa_e_lista_as_regras(self):
        self._tipo("1")
        with self.assertRaises(UserError) as erro:
            self._s1010()._to_esociallib_dict()
        mensagem = str(erro.exception)
        self.assertIn("11 a 14", mensagem)
        self.assertIn("700 a 704", mensagem)
        self.assertIn("DESC_CONVENIO", mensagem)

    def test_desconto_e_informativa_seguem_com_09(self):
        for tipo in ("2", "3", "4"):
            self._tipo(tipo)
            s1010 = self._s1010()
            self.assertEqual(s1010._to_esociallib_dict()["cod_inc_irrf"], 9)
            s1010.unlink()

    def test_vencimento_com_escolha_gera(self):
        self._tipo("1")
        for codigo, esperado in (("11", 11), ("70", 70), ("09", 9)):
            self.rule.l10n_br_esocial_cod_inc_irrf = codigo
            s1010 = self._s1010()
            self.assertEqual(s1010._to_esociallib_dict()["cod_inc_irrf"], esperado)
            s1010.unlink()

    def test_criar_para_regras_lista_todas_de_uma_vez(self):
        self._tipo("1")
        outra = self.env["hr.salary.rule"].search([("id", "!=", self.rule.id)], limit=1)
        outra.write(
            {
                "l10n_br_esocial_cod_rubr": "OUTRA_VENC",
                "l10n_br_esocial_tp_rubr": "1",
                "l10n_br_esocial_cod_inc_irrf": False,
            }
        )
        with self.assertRaises(UserError) as erro:
            self.env["l10n_br.esocial.s1010"].criar_para_regras(
                self.rule | outra, "2024-01"
            )
        mensagem = str(erro.exception)
        self.assertIn("DESC_CONVENIO", mensagem)
        self.assertIn("OUTRA_VENC", mensagem)

    def test_exclusao_nao_exige_incidencia(self):
        self._tipo("1")
        s1010 = self._s1010()
        s1010.operacao = "exclusao"
        self.assertNotIn("cod_inc_irrf", s1010._to_esociallib_dict())
