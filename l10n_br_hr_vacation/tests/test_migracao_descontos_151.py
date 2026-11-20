# Copyright 2026 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""TG-151: upgrade da 1.10.0 até a atual deixa as 3 regras de desconto atuais.

As migrações 1.11.0 (TG-136) e 1.12.0 (TG-133) derivavam a fórmula "antiga" do
XML final e, juntas, pulavam a regra gravada pela 1.10.0 como se fosse
personalizada. A 1.17.0 reconhece as fórmulas de cada versão anterior.
"""
import importlib.util

from odoo.tests import tagged
from odoo.tools import file_path

from .common import VacationCommon

XMLIDS = (
    "hr_rule_desconto_art_480",
    "hr_rule_desconto_aviso_previo",
    "hr_rule_desconto_13_excesso",
)


def _carrega(versao):
    caminho = file_path(f"l10n_br_hr_vacation/migrations/{versao}/post-migration.py")
    spec = importlib.util.spec_from_file_location(f"mig_151_{versao}", caminho)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


@tagged("post_install", "-at_install")
class TestMigracaoDescontos151(VacationCommon):
    def _regra(self, xmlid):
        return self.env.ref(f"l10n_br_hr_vacation.{xmlid}")

    def _formulas_antigas(self, indice):
        """Fórmulas gravadas pela 1.10.0 (0) ou pela 1.11.0 (1)."""
        return {x: _carrega("18.0.1.17.0").REGRAS[x][indice] for x in XMLIDS}

    def _grava(self, formulas):
        for xmlid, formula in formulas.items():
            self._regra(xmlid).amount_python_compute = formula

    def _atuais(self):
        return {x: self._regra(x).amount_python_compute for x in XMLIDS}

    def _migra(self, versao, de):
        _carrega(versao).migrate(self.env.cr, de)

    def _sobe_ate_a_1_16(self):
        """As migrações que existiam antes da TG-151, na ordem do upgrade."""
        self._migra("18.0.1.11.0", "18.0.1.10.0")
        self._migra("18.0.1.12.0", "18.0.1.11.0")

    def test_formulas_antigas_sao_as_da_1_10_e_da_1_11(self):
        v10 = self._formulas_antigas(0)
        v11 = self._formulas_antigas(1)
        for xmlid in XMLIDS:
            self.assertNotIn("DECIMO_AVISO_INDENIZADO", v10[xmlid])
            self.assertIn("DECIMO_AVISO_INDENIZADO", v11[xmlid])
            for antiga in (v10[xmlid], v11[xmlid]):
                self.assertIn("adicionais_fixos(contract)", antiga)
                self.assertNotIn("'momento'", antiga)

    def test_migracoes_antigas_sozinhas_deixam_a_1_10_como_estava(self):
        """Reproduz o defeito: 1.11.0 e 1.12.0 não reconhecem a 1.10.0."""
        v10 = self._formulas_antigas(0)
        self._grava(v10)
        self._sobe_ate_a_1_16()
        self.assertEqual(self._atuais(), v10)

    def test_upgrade_da_1_10_ate_a_atual(self):
        novas = self._atuais()
        self._grava(self._formulas_antigas(0))
        self._sobe_ate_a_1_16()
        self._migra("18.0.1.17.0", "18.0.1.16.0")
        self.assertEqual(self._atuais(), novas)
        for formula in novas.values():
            self.assertIn("DECIMO_AVISO_INDENIZADO", formula)
            self.assertIn("adicionais_fixos(contract, 'momento')", formula)

    def test_upgrade_da_1_11_ate_a_atual(self):
        novas = self._atuais()
        self._grava(self._formulas_antigas(1))
        self._migra("18.0.1.17.0", "18.0.1.16.0")
        self.assertEqual(self._atuais(), novas)

    def test_banco_atual_fica_igual_e_sem_aviso(self):
        antes = {x: self._regra(x).read()[0] for x in XMLIDS}
        with self.assertNoLogs("mig_151_18.0.1.17.0", "WARNING"):
            self._migra("18.0.1.17.0", "18.0.1.16.0")
        for xmlid in XMLIDS:
            self.assertEqual(self._regra(xmlid).read()[0], antes[xmlid], xmlid)

    def test_migracao_e_idempotente(self):
        self._grava(self._formulas_antigas(0))
        self._migra("18.0.1.17.0", "18.0.1.16.0")
        apos_a_primeira = self._atuais()
        self._migra("18.0.1.17.0", "18.0.1.16.0")
        self.assertEqual(self._atuais(), apos_a_primeira)

    def test_regra_personalizada_e_preservada_com_aviso(self):
        novas = self._atuais()
        self._grava(self._formulas_antigas(0))
        regra = self._regra("hr_rule_desconto_aviso_previo")
        regra.amount_python_compute = "result = 123.0"
        with self.assertLogs("mig_151_18.0.1.17.0", "WARNING") as logs:
            self._migra("18.0.1.17.0", "18.0.1.16.0")
        self.assertEqual(len(logs.output), 1)
        self.assertIn("personalizada", logs.output[0])
        self.assertIn("DESCONTO_AVISO_PREVIO", logs.output[0].upper().replace(" ", "_"))
        self.assertEqual(regra.amount_python_compute, "result = 123.0")
        # As outras duas, padrão da 1.10.0, são atualizadas.
        for xmlid in ("hr_rule_desconto_art_480", "hr_rule_desconto_13_excesso"):
            self.assertEqual(self._regra(xmlid).amount_python_compute, novas[xmlid])

    def test_personalizada_com_a_chamada_antiga_nao_e_trocada(self):
        """Um ajuste do cliente sobre a 1.10.0 não é confundido com a padrão."""
        v10 = self._formulas_antigas(0)["hr_rule_desconto_art_480"]
        ajustada = v10.replace("round_money(max(", "round_money(1 + max(")
        self.assertNotEqual(ajustada, v10)
        regra = self._regra("hr_rule_desconto_art_480")
        regra.amount_python_compute = ajustada
        with self.assertLogs("mig_151_18.0.1.17.0", "WARNING"):
            self._migra("18.0.1.17.0", "18.0.1.16.0")
        self.assertEqual(regra.amount_python_compute, ajustada)

    def test_aviso_da_1_12_nao_fala_em_media_para_a_verba_momento(self):
        self._grava(self._formulas_antigas(0))
        with self.assertLogs("mig_151_18.0.1.12.0", "WARNING") as logs:
            self._migra("18.0.1.12.0", "18.0.1.11.0")
        for saida in logs.output:
            if "DESCONTO" in saida:
                self.assertNotIn("para a média", saida)
                self.assertIn("'momento'", saida)
