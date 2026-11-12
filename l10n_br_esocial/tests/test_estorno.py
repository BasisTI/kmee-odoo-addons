# Copyright 2024 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""TG-132: holerite estornado não vai ao eSocial; o evento dele se retifica."""

from odoo.exceptions import UserError
from odoo.tests import tagged

from .common import HAS_ESOCIALLIB, RECIBO_S1200, RECIBO_S1210, ESocialCicloCommon

RECIBO_RETIF = "1.2.0000000000000054321"


@tagged("post_install", "-at_install")
class TestEstornoEsocial(ESocialCicloCommon):
    def _aceitar(self, evento, recibo):
        evento.write({"state": "success", "nr_recibo": recibo})

    def _estornar(self, payslip):
        payslip.refund_sheet()
        return payslip.refunded_id

    # ── Geração e conferência ignoram o par ────────────────────────────────

    def test_geracao_recusa_holerite_fora_de_vigor(self):
        original = self._criar_payslip()
        estorno = self._estornar(original)
        for slip in (original, estorno):
            with self.assertRaises(UserError):
                slip.action_esocial_gerar_s1200()
            with self.assertRaises(UserError):
                slip.action_esocial_gerar_s1210()

    def test_geracao_ignora_o_par_e_usa_o_novo(self):
        if not HAS_ESOCIALLIB:
            self.skipTest("esociallib não instalada")
        original = self._criar_payslip()
        estorno = self._estornar(original)
        novo = self._criar_payslip()
        (original | estorno | novo).action_esocial_gerar_s1200()
        s1200 = novo.l10n_br_esocial_s1200_id
        self.assertEqual(s1200.payslip_ids, novo)
        self.assertFalse(original.l10n_br_esocial_s1200_id)
        self.assertFalse(estorno.l10n_br_esocial_s1200_id)

    def test_conferencia_ignora_o_par(self):
        original = self._criar_payslip()
        estorno = self._estornar(original)
        novo = self._criar_payslip()
        conferencia = self.env["l10n_br.esocial.conferencia"].create(
            {"company_id": self.company.id, "per_apur": "2024-03"}
        )
        slips = conferencia._buscar_payslips()
        self.assertIn(novo, slips)
        self.assertNotIn(original, slips)
        self.assertNotIn(estorno, slips)

    # ── Aviso "a retificar" ────────────────────────────────────────────────

    def test_estornado_com_evento_fica_a_retificar(self):
        if not HAS_ESOCIALLIB:
            self.skipTest("esociallib não instalada")
        original = self._criar_payslip()
        original.action_esocial_gerar_s1200()
        self.assertFalse(original.l10n_br_esocial_a_retificar)
        estorno = self._estornar(original)
        self.assertTrue(original.l10n_br_esocial_a_retificar)
        self.assertFalse(estorno.l10n_br_esocial_a_retificar)

    def test_estornado_sem_evento_nao_tem_aviso(self):
        original = self._criar_payslip()
        self._estornar(original)
        self.assertFalse(original.l10n_br_esocial_a_retificar)

    # ── Retificação do S-1200 ──────────────────────────────────────────────

    def _cenario_s1200_aceito(self):
        original = self._criar_payslip()
        original.action_esocial_gerar_s1200()
        s1200_orig = original.l10n_br_esocial_s1200_id
        self._aceitar(s1200_orig.evento_id, RECIBO_S1200)
        self._estornar(original)
        novo = self._criar_payslip()
        return original, s1200_orig, novo

    def test_novo_holerite_retifica_o_s1200_aceito_do_estornado(self):
        if not HAS_ESOCIALLIB:
            self.skipTest("esociallib não instalada")
        original, s1200_orig, novo = self._cenario_s1200_aceito()
        novo.action_esocial_gerar_s1200()
        s1200 = novo.l10n_br_esocial_s1200_id
        self.assertNotEqual(s1200, s1200_orig)
        self.assertEqual(s1200.ind_retif, "2")
        self.assertEqual(s1200.nr_recibo, RECIBO_S1200)
        self.assertEqual(s1200.payslip_ids, novo)
        evento = s1200.evento_id
        self.assertEqual(evento.ind_retif, "2")
        self.assertEqual(evento.operacao, "R")
        self.assertEqual(evento.evento_retificado_id, s1200_orig.evento_id)
        self.assertIn(RECIBO_S1200, evento.xml_envio)

    def test_aceite_do_retificador_marca_o_anterior_retificado(self):
        if not HAS_ESOCIALLIB:
            self.skipTest("esociallib não instalada")
        original, s1200_orig, novo = self._cenario_s1200_aceito()
        novo.action_esocial_gerar_s1200()
        evento = novo.l10n_br_esocial_s1200_id.evento_id
        evento.registrar_aceite(nr_recibo=RECIBO_RETIF)
        self.assertEqual(s1200_orig.evento_id.state, "rectified")
        self.assertFalse(original.l10n_br_esocial_a_retificar)

    def test_retificador_leva_os_holerites_que_continuam_em_vigor(self):
        if not HAS_ESOCIALLIB:
            self.skipTest("esociallib não instalada")
        a = self._criar_payslip()
        b = self._criar_payslip()
        (a | b).action_esocial_gerar_s1200()
        s1200_orig = a.l10n_br_esocial_s1200_id
        self.assertEqual(s1200_orig.payslip_ids, a | b)
        self._aceitar(s1200_orig.evento_id, RECIBO_S1200)
        self._estornar(a)
        novo = self._criar_payslip()
        novo.action_esocial_gerar_s1200()
        s1200 = novo.l10n_br_esocial_s1200_id
        self.assertEqual(s1200.payslip_ids, b | novo)
        self.assertEqual(b.l10n_br_esocial_s1200_id, s1200)

    def test_sem_recibo_a_geracao_espera_o_retorno(self):
        if not HAS_ESOCIALLIB:
            self.skipTest("esociallib não instalada")
        original = self._criar_payslip()
        original.action_esocial_gerar_s1200()
        original.l10n_br_esocial_s1200_id.evento_id.write({"state": "sent"})
        self._estornar(original)
        novo = self._criar_payslip()
        with self.assertRaises(UserError):
            novo.action_esocial_gerar_s1200()

    def test_sem_evento_anterior_gera_original(self):
        if not HAS_ESOCIALLIB:
            self.skipTest("esociallib não instalada")
        original = self._criar_payslip()
        self._estornar(original)
        novo = self._criar_payslip()
        novo.action_esocial_gerar_s1200()
        s1200 = novo.l10n_br_esocial_s1200_id
        self.assertEqual(s1200.ind_retif, "1")
        self.assertFalse(s1200.nr_recibo)

    # ── Retificação do S-1210 ──────────────────────────────────────────────

    def test_s1210_do_novo_retifica_o_aceito_do_estornado(self):
        if not HAS_ESOCIALLIB:
            self.skipTest("esociallib não instalada")
        original = self._criar_payslip(data_pagamento="2024-04-05")
        original.action_esocial_gerar_s1200()
        self._aceitar(original.l10n_br_esocial_s1200_id.evento_id, RECIBO_S1200)
        original.action_esocial_gerar_s1210()
        s1210_orig = original.l10n_br_esocial_s1210_id
        self._aceitar(s1210_orig.evento_id, RECIBO_S1210)
        self._estornar(original)
        novo = self._criar_payslip(data_pagamento="2024-04-10")
        novo.action_esocial_gerar_s1200()
        self._aceitar(novo.l10n_br_esocial_s1200_id.evento_id, RECIBO_RETIF)
        novo.action_esocial_gerar_s1210()
        s1210 = novo.l10n_br_esocial_s1210_id
        self.assertEqual(s1210.ind_retif, "2")
        self.assertEqual(s1210.nr_recibo, RECIBO_S1210)
        self.assertEqual(s1210.pagamento_ids.payslip_id, novo)
        self.assertEqual(s1210.evento_id.evento_retificado_id, s1210_orig.evento_id)
        s1210.evento_id.registrar_aceite(nr_recibo=RECIBO_RETIF)
        self.assertEqual(s1210_orig.evento_id.state, "rectified")
