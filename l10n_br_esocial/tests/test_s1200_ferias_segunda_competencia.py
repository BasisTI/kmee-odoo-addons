# Copyright 2026 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""TG-152: o holerite que gera dois S-1200 não depende só do primeiro.

Retificar e excluir (S-3000) a segunda competência sozinha; a primeira não muda.
"""

from odoo.tests import tagged

from .common import HAS_ESOCIALLIB, ESocialCicloCommon

RECIBO_NOV = "1.2.0000000000000011111"
RECIBO_DEZ = "1.2.0000000000000022222"
RECIBO_RETIF = "1.2.0000000000000033333"


@tagged("post_install", "-at_install")
class TestS1200FeriasSegundaCompetencia(ESocialCicloCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.employee.write({"cnpj_cpf": "111.444.777-35"})
        cls.estrutura = cls.env["hr.payroll.structure"].search(
            [("code", "=", "FERIAS")], limit=1
        ) or cls.env["hr.payroll.structure"].create(
            {"name": "Férias (teste)", "code": "FERIAS"}
        )

    def _recibo(self, valor=3100.0):
        slip = self._criar_payslip(linhas=[("FERIAS", valor), ("NET", valor)])
        slip.write(
            {
                "struct_id": self.estrutura.id,
                "date_from": "2026-11-10",
                "date_to": "2026-12-10",
                "l10n_br_esocial_data_pagamento": "2026-11-05",
            }
        )
        return slip

    def _gera_e_aceita(self):
        if not HAS_ESOCIALLIB:
            self.skipTest("esociallib não instalada")
        recibo = self._recibo()
        recibo.action_esocial_gerar_s1200()
        s1200s = recibo.l10n_br_esocial_s1200_ids
        nov = s1200s.filtered(lambda s: s.per_apur == "2026-11")
        dez = s1200s.filtered(lambda s: s.per_apur == "2026-12")
        nov.evento_id.write({"state": "success", "nr_recibo": RECIBO_NOV})
        dez.evento_id.write({"state": "success", "nr_recibo": RECIBO_DEZ})
        return recibo, nov, dez

    def test_recibo_tem_um_s1200_por_competencia_e_o_principal_e_o_primeiro(self):
        recibo, nov, dez = self._gera_e_aceita()
        self.assertEqual(len(recibo.l10n_br_esocial_s1200_ids), 2)
        self.assertEqual(recibo.l10n_br_esocial_s1200_id, nov)
        self.assertEqual(nov.payslip_ids, recibo)
        self.assertEqual(dez.payslip_ids, recibo)

    def test_retifica_so_a_segunda_competencia(self):
        recibo, nov, dez = self._gera_e_aceita()
        recibo.refund_sheet()
        self.assertTrue(recibo.l10n_br_esocial_a_retificar)
        novo = self._recibo()
        novo.with_context(esocial_per_apur="2026-12").action_esocial_gerar_s1200()
        retificador = novo.l10n_br_esocial_s1200_ids
        self.assertEqual(retificador.per_apur, "2026-12")
        # O recibo novo aponta para o S-1200 vigente da competência do pagamento
        # (a primeira, inalterada): sem isso o S-1210 dele recusa.
        self.assertEqual(novo.l10n_br_esocial_s1200_id, nov)
        self.assertEqual(retificador.ind_retif, "2")
        self.assertEqual(retificador.nr_recibo, RECIBO_DEZ)
        # A primeira competência não muda: o evento aceito segue como está e
        # não há retificador dela.
        self.assertEqual(nov.evento_id.state, "success")
        self.assertFalse(
            self.env["l10n_br.esocial.s1200"].search(
                [("per_apur", "=", "2026-11"), ("ind_retif", "=", "2")]
            )
        )

    def test_acao_por_competencia_sem_contexto(self):
        recibo, nov, dez = self._gera_e_aceita()
        recibo.refund_sheet()
        novo = self._recibo()
        novo.action_esocial_gerar_s1200_competencia("2026-12")
        self.assertEqual(novo.l10n_br_esocial_s1200_ids.per_apur, "2026-12")
        self.assertEqual(nov.evento_id.state, "success")

    def test_exclui_so_a_segunda_competencia(self):
        if not HAS_ESOCIALLIB:
            self.skipTest("esociallib não instalada")
        recibo, nov, dez = self._gera_e_aceita()
        s3000 = self.env["l10n_br.esocial.s3000"].create(
            {
                "evento_origem_id": dez.evento_id.id,
                "company_id": self.company.id,
                "per_apur": "2026-12",
                "ind_apuracao": "1",
                "cpf_trab": self.cpf_employee,
            }
        )
        evento = s3000.action_gerar_evento()
        evento.registrar_aceite(nr_recibo=RECIBO_RETIF)
        self.assertEqual(dez.evento_id.state, "excluded")
        self.assertEqual(nov.evento_id.state, "success")
        self.assertEqual(recibo.l10n_br_esocial_s1200_id, nov)
        # Com a segunda excluída, só a primeira segue vigente no holerite.
        self.assertEqual(recibo._esocial_s1200_vigentes(), nov.evento_id)
