# Copyright 2026 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""TG-96: o mtvDeslig do S-2299 vem da causa da rescisão, senão do contrato."""

from unittest import mock

from odoo.tests import tagged

from .common import ESocialCicloCommon


@tagged("post_install", "-at_install")
class TestMotivoDesligamentoPayslip(ESocialCicloCommon):
    def test_sem_modulo_de_rescisao_vale_o_contrato(self):
        motivo = self.env.ref("l10n_br_esocial.mot_deslig_02")
        self.contract.l10n_br_esocial_motivo_deslig_id = motivo
        payslip = self._criar_payslip()
        self.assertEqual(payslip._esocial_motivo_desligamento(), motivo)

    def test_causa_da_rescisao_prevalece_sobre_o_contrato(self):
        self.contract.l10n_br_esocial_motivo_deslig_id = self.env.ref(
            "l10n_br_esocial.mot_deslig_02"
        )
        payslip = self._criar_payslip()
        with mock.patch.object(
            type(payslip),
            "_l10n_br_motivo_desligamento_esocial",
            lambda self: "33",
            create=True,
        ):
            self.assertEqual(
                payslip._esocial_motivo_desligamento(),
                self.env.ref("l10n_br_esocial.mot_deslig_33"),
            )

    def test_rescisao_sem_tipo_cai_no_contrato(self):
        motivo = self.env.ref("l10n_br_esocial.mot_deslig_02")
        self.contract.l10n_br_esocial_motivo_deslig_id = motivo
        payslip = self._criar_payslip()
        with mock.patch.object(
            type(payslip),
            "_l10n_br_motivo_desligamento_esocial",
            lambda self: False,
            create=True,
        ):
            self.assertEqual(payslip._esocial_motivo_desligamento(), motivo)
