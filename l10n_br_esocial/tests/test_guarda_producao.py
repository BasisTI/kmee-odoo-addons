# Copyright 2025 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from unittest import mock

from odoo.exceptions import UserError, ValidationError
from odoo.tests.common import TransactionCase

LOTE = "odoo.addons.l10n_br_esocial.models.esocial_lote"
PARAM = "l10n_br_esocial.permitir_producao"


class TestGuardaProducao(TransactionCase):
    """A produção do eSocial só abre com configuração explícita."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.company.l10n_br_esocial_tp_amb = "2"
        cls.env["ir.config_parameter"].sudo().set_param(PARAM, False)

    def _lote(self, tp_amb_xml="2", state="validated"):
        evento = self.env["l10n_br.esocial.evento"].create(
            {
                "tipo": "S-1200",
                "operacao": "I",
                "state": state,
                "company_id": self.company.id,
                "xml_envio": f"<eSocial><tpAmb>{tp_amb_xml}</tpAmb></eSocial>",
            }
        )
        lote = self.env["l10n_br.esocial.lote"].create(
            {"company_id": self.company.id, "protocolo": "PROT-1"}
        )
        evento.lote_id = lote.id
        return lote

    def _libera(self):
        self.env["ir.config_parameter"].sudo().set_param(PARAM, "True")

    def test_padrao_e_producao_restrita(self):
        self.assertEqual(self.company.l10n_br_esocial_tp_amb, "2")
        self.assertFalse(self.env["res.company"]._esocial_producao_permitida())

    def test_empresa_nao_aceita_producao_sem_configuracao(self):
        with self.assertRaises(ValidationError):
            self.company.l10n_br_esocial_tp_amb = "1"

    def test_empresa_aceita_producao_com_configuracao(self):
        self._libera()
        self.company.l10n_br_esocial_tp_amb = "1"
        self.assertEqual(self.company.l10n_br_esocial_tp_amb, "1")

    def test_transmitir_bloqueia_xml_de_producao(self):
        lote = self._lote(tp_amb_xml="1")
        with mock.patch(f"{LOTE}.enviar_lote") as enviar, mock.patch(
            f"{LOTE}.assinar"
        ), self.assertRaisesRegex(UserError, "bloqueada"):
            lote.action_transmitir()
        enviar.assert_not_called()
        self.assertEqual(lote.state, "draft")

    def test_consultar_bloqueia_xml_de_producao(self):
        lote = self._lote(tp_amb_xml="1")
        with mock.patch(f"{LOTE}.consultar_lote") as consultar, mock.patch.object(
            type(lote), "_get_certificate", return_value=(b"", "")
        ), self.assertRaisesRegex(UserError, "bloqueada"):
            lote.action_consultar()
        consultar.assert_not_called()

    def test_empresa_em_producao_legada_bloqueia(self):
        """Empresa que já estava em 1 antes da trava não transmite nem consulta."""
        self._libera()
        self.company.l10n_br_esocial_tp_amb = "1"
        self.env["ir.config_parameter"].sudo().set_param(PARAM, False)
        lote = self._lote(tp_amb_xml="1")
        with mock.patch(f"{LOTE}.consultar_lote") as consultar, mock.patch.object(
            type(lote), "_get_certificate", return_value=(b"", "")
        ), self.assertRaisesRegex(UserError, "bloqueada"):
            lote.action_consultar()
        consultar.assert_not_called()

    def test_producao_liberada_e_consistente_passa(self):
        self._libera()
        self.company.l10n_br_esocial_tp_amb = "1"
        lote = self._lote(tp_amb_xml="1")
        fake = mock.Mock(status="em_processamento", eventos=[])
        with mock.patch(f"{LOTE}.consultar_lote", return_value=fake), mock.patch.object(
            type(lote), "_get_certificate", return_value=(b"", "")
        ):
            lote.action_consultar()
        self.assertEqual(lote.state, "processing")

    def test_producao_liberada_xml_divergente_bloqueia(self):
        """XML restrito com empresa em produção (ou o inverso) não vai embora."""
        self._libera()
        self.company.l10n_br_esocial_tp_amb = "1"
        lote = self._lote(tp_amb_xml="2")
        with mock.patch(f"{LOTE}.consultar_lote") as consultar, mock.patch.object(
            type(lote), "_get_certificate", return_value=(b"", "")
        ), self.assertRaisesRegex(UserError, "Gere o evento novamente"):
            lote.action_consultar()
        consultar.assert_not_called()

    def test_restrita_passa(self):
        lote = self._lote(tp_amb_xml="2")
        fake = mock.Mock(status="em_processamento", eventos=[])
        with mock.patch(f"{LOTE}.consultar_lote", return_value=fake), mock.patch.object(
            type(lote), "_get_certificate", return_value=(b"", "")
        ):
            lote.action_consultar()
        self.assertEqual(lote.state, "processing")
