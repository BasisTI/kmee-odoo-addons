# Copyright 2024 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""TG-132: holerite estornado não vai ao eSocial; o evento dele se retifica."""

from odoo.exceptions import UserError
from odoo.tests import tagged

from .common import (
    HAS_ESOCIALLIB,
    RECIBO_S1200,
    RECIBO_S1210,
    RECIBO_S1299,
    ESocialCicloCommon,
    retorno_s5001,
)

RECIBO_RETIF = "1.2.0000000000000054321"


@tagged("post_install", "-at_install")
class TestEstornoEsocial(ESocialCicloCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # O estorno recria o holerite e valida o CPF; o do cenário comum não passa
        # nos dígitos verificadores.
        cls.employee.write({"cnpj_cpf": "111.444.777-35"})

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
        # Mesma estrutura e período não convivem (validação de período); o
        # segundo holerite, em outra estrutura, vai no mesmo S-1200 da competência.
        base = a.struct_id or self.env["hr.payroll.structure"].search([], limit=1)
        outra = base.copy({"name": "Estrutura B (estorno eSocial)"})
        b = self._criar_payslip(struct_id=outra.id)
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

    # ── S-1210 transmitido: exclusão prévia (MOS S-1.3, cap. I item 15.2) ──

    def _cenario_s1210_aceito(self):
        original = self._criar_payslip(data_pagamento="2024-04-05")
        original.action_esocial_gerar_s1200()
        self._aceitar(original.l10n_br_esocial_s1200_id.evento_id, RECIBO_S1200)
        original.action_esocial_gerar_s1210()
        s1210 = original.l10n_br_esocial_s1210_id
        self._aceitar(s1210.evento_id, RECIBO_S1210)
        self._estornar(original)
        novo = self._criar_payslip(data_pagamento="2024-04-10")
        return original, s1210, novo

    def test_retificador_exige_excluir_antes_o_s1210_transmitido(self):
        if not HAS_ESOCIALLIB:
            self.skipTest("esociallib não instalada")
        original, s1210, novo = self._cenario_s1210_aceito()
        with self.assertRaisesRegex(UserError, "S-3000"):
            novo.action_esocial_gerar_s1200()
        # S-1210 excluído (S-3000 aceito): o retificador sai.
        s1210.evento_id.write({"state": "excluded"})
        novo.action_esocial_gerar_s1200()
        self.assertEqual(novo.l10n_br_esocial_s1200_id.ind_retif, "2")

    def test_s1210_do_novo_sai_como_original_apos_a_exclusao(self):
        if not HAS_ESOCIALLIB:
            self.skipTest("esociallib não instalada")
        original, s1210, novo = self._cenario_s1210_aceito()
        s1210.evento_id.write({"state": "excluded"})
        novo.action_esocial_gerar_s1200()
        self._aceitar(novo.l10n_br_esocial_s1200_id.evento_id, RECIBO_RETIF)
        novo.action_esocial_gerar_s1210()
        self.assertEqual(novo.l10n_br_esocial_s1210_id.ind_retif, "1")

    # ── Conferência: só o totalizador do evento vigente ────────────────────

    def test_conferencia_nao_soma_totalizador_do_retificado(self):
        if not HAS_ESOCIALLIB:
            self.skipTest("esociallib não instalada")
        cpf = "11144477735"
        original = self._criar_payslip()
        original.action_esocial_gerar_s1200()
        ev1 = original.l10n_br_esocial_s1200_id.evento_id
        ev1.registrar_aceite(
            nr_recibo=RECIBO_S1200, retorno_xml=retorno_s5001(cpf, inss=330.0)
        )
        self._estornar(original)
        novo = self._criar_payslip()
        novo.action_esocial_gerar_s1200()
        novo.l10n_br_esocial_s1200_id.evento_id.registrar_aceite(
            nr_recibo=RECIBO_RETIF, retorno_xml=retorno_s5001(cpf, inss=330.0)
        )
        self.assertEqual(ev1.state, "rectified")
        conferencia = self.env["l10n_br.esocial.conferencia"].create(
            {"company_id": self.company.id, "per_apur": "2024-03"}
        )
        conferencia.action_apurar()
        linha = conferencia.linha_ids.filtered(lambda r: r.indicador == "inss_segurado")
        self.assertAlmostEqual(linha.valor_totalizador, 330.0, places=2)
        self.assertFalse(linha.divergente)

    # ── Duplicar o estornado não herda os eventos ──────────────────────────

    def test_duplicar_nao_herda_os_eventos(self):
        if not HAS_ESOCIALLIB:
            self.skipTest("esociallib não instalada")
        original, s1210, novo = self._cenario_s1210_aceito()
        novo.write({"state": "cancel"})
        copia = original.copy()
        self.assertFalse(copia.l10n_br_esocial_s1200_id)
        self.assertFalse(copia.l10n_br_esocial_s1210_id)

    # ── Evento não transmitido do estornado ────────────────────────────────

    def test_evento_em_rascunho_do_estornado_nao_valida(self):
        if not HAS_ESOCIALLIB:
            self.skipTest("esociallib não instalada")
        original = self._criar_payslip()
        original.action_esocial_gerar_s1200()
        evento = original.l10n_br_esocial_s1200_id.evento_id
        self._estornar(original)
        self.assertTrue(original.l10n_br_esocial_a_retificar)
        with self.assertRaisesRegex(UserError, "fora de vigor"):
            evento.action_validate()

    def test_evento_validado_do_estornado_sai_do_lote(self):
        if not HAS_ESOCIALLIB:
            self.skipTest("esociallib não instalada")
        original = self._criar_payslip()
        original.action_esocial_gerar_s1200()
        evento = original.l10n_br_esocial_s1200_id.evento_id
        evento.action_validate()
        lote = self.env["l10n_br.esocial.lote"].create({"company_id": self.company.id})
        lote.action_add_validated_events()
        self.assertEqual(evento.lote_id, lote)
        self._estornar(original)
        self.assertEqual(evento.state, "draft")
        self.assertFalse(evento.lote_id)

    # ── Menores ────────────────────────────────────────────────────────────

    def test_segunda_chamada_nao_duplica_o_retificador(self):
        if not HAS_ESOCIALLIB:
            self.skipTest("esociallib não instalada")
        original, s1200_orig, novo = self._cenario_s1200_aceito()
        novo.action_esocial_gerar_s1200()
        primeiro = novo.l10n_br_esocial_s1200_id
        with self.assertRaisesRegex(UserError, "retificador"):
            novo.action_esocial_gerar_s1200()
        self.assertEqual(novo.l10n_br_esocial_s1200_id, primeiro)
        retificadores = self.env["l10n_br.esocial.s1200"].search(
            [("ind_retif", "=", "2"), ("nr_recibo", "=", RECIBO_S1200)]
        )
        self.assertEqual(retificadores, primeiro)

    def test_s2299_do_estornado_fica_marcado_e_a_mensagem_explica(self):
        if not HAS_ESOCIALLIB:
            self.skipTest("esociallib não instalada")
        self.contract.l10n_br_esocial_motivo_deslig_id = self.env.ref(
            "l10n_br_esocial.mot_deslig_02"
        )
        estrutura = self.env["hr.payroll.structure"].create(
            {"name": "Rescisão estorno", "code": "RESCISAO"}
        )
        rescisao = self._criar_payslip(struct_id=estrutura.id)
        rescisao.action_esocial_gerar_s2299()
        self.assertTrue(rescisao.l10n_br_esocial_s2299_ids)
        self.assertFalse(rescisao.l10n_br_esocial_a_retificar)
        self._estornar(rescisao)
        self.assertTrue(rescisao.l10n_br_esocial_a_retificar)
        with self.assertRaisesRegex(UserError, "fora de vigor"):
            rescisao.action_esocial_gerar_s2299()

    def test_marcacao_e_pesquisavel(self):
        if not HAS_ESOCIALLIB:
            self.skipTest("esociallib não instalada")
        original = self._criar_payslip()
        original.action_esocial_gerar_s1200()
        self._estornar(original)
        outro = self._criar_payslip()
        achados = self.env["hr.payslip"].search(
            [("l10n_br_esocial_a_retificar", "=", True)]
        )
        self.assertIn(original, achados)
        self.assertNotIn(outro, achados)

    def test_aceite_forcado_propaga_a_retificacao(self):
        if not HAS_ESOCIALLIB:
            self.skipTest("esociallib não instalada")
        original, s1200_orig, novo = self._cenario_s1200_aceito()
        novo.action_esocial_gerar_s1200()
        novo.l10n_br_esocial_s1200_id.evento_id.action_mark_success()
        self.assertEqual(s1200_orig.evento_id.state, "rectified")

    def test_competencia_fechada_bloqueia_ate_a_reabertura(self):
        if not HAS_ESOCIALLIB:
            self.skipTest("esociallib não instalada")
        self._criar_evento("S-1299", per_apur="2024-03", nr_recibo=RECIBO_S1299)
        payslip = self._criar_payslip()
        with self.assertRaisesRegex(UserError, "S-1298"):
            payslip.action_esocial_gerar_s1200()
        self._criar_evento("S-1298", per_apur="2024-03", nr_recibo=RECIBO_S1299)
        payslip.action_esocial_gerar_s1200()
        self.assertTrue(payslip.l10n_br_esocial_s1200_id)

    # ── Estorno cancelado ──────────────────────────────────────────────────

    def test_estorno_cancelado_antes_da_retificacao_apaga_o_aviso(self):
        if not HAS_ESOCIALLIB:
            self.skipTest("esociallib não instalada")
        original = self._criar_payslip()
        original.action_esocial_gerar_s1200()
        estorno = self._estornar(original)
        self.assertTrue(original.l10n_br_esocial_a_retificar)
        estorno.write({"state": "cancel"})
        self.assertFalse(original.l10n_br_fora_de_vigor)
        self.assertFalse(original.l10n_br_esocial_a_retificar)

    def test_estorno_cancelado_depois_da_retificacao_deixa_o_original_sem_evento(
        self,
    ):
        if not HAS_ESOCIALLIB:
            self.skipTest("esociallib não instalada")
        original, s1200_orig, novo = self._cenario_s1200_aceito()
        novo.action_esocial_gerar_s1200()
        novo.l10n_br_esocial_s1200_id.evento_id.registrar_aceite(nr_recibo=RECIBO_RETIF)
        original.refunded_id.write({"state": "cancel"})
        self.assertFalse(original.l10n_br_fora_de_vigor)
        conferencia = self.env["l10n_br.esocial.conferencia"].create(
            {"company_id": self.company.id, "per_apur": "2024-03"}
        )
        # O original voltou a valer, mas o evento dele foi retificado pelo do
        # novo: a conferência o aponta como sem evento aceito.
        self.assertIn(original, conferencia.payslip_sem_evento_ids)
