# Copyright 2026 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""TG-96: o mtvDeslig do S-2299 vem da causa da rescisão, senão do contrato."""

from odoo.tests import tagged
from odoo.tools import mute_logger

from .common import HAS_ESOCIALLIB, ESocialCicloCommon


@tagged("post_install", "-at_install")
class TestMotivoDesligamentoPayslip(ESocialCicloCommon):
    def _rescisao(self, **vals):
        estrutura = self.env["hr.payroll.structure"].create(
            {"name": "Rescisão motivo", "code": "RESCISAO"}
        )
        payslip = self._criar_payslip(struct_id=estrutura.id)
        if vals:
            payslip.write(vals)
        return payslip

    def _gerar(self, payslip):
        with mute_logger(
            "odoo.addons.l10n_br_esocial.models.intermediarios.s2299_desligamento"
        ):
            payslip.action_esocial_gerar_s2299()
        return payslip.l10n_br_esocial_s2299_ids

    def test_sem_tipo_vale_o_motivo_do_contrato(self):
        motivo = self.env.ref("l10n_br_esocial.mot_deslig_02")
        self.contract.l10n_br_esocial_motivo_deslig_id = motivo
        payslip = self._rescisao()
        self.assertEqual(payslip._esocial_motivo_desligamento(), motivo)

    def test_s2299_gerado_usa_o_motivo_da_causa(self):
        """S-2299 de verdade: culpa recíproca (05) prevalece sobre o contrato."""
        if "l10n_br_tipo_rescisao" not in self.env["hr.payslip"]._fields:
            self.skipTest("l10n_br_hr_vacation não instalado")
        if not HAS_ESOCIALLIB:
            self.skipTest("esociallib não instalada")
        self.contract.l10n_br_esocial_motivo_deslig_id = self.env.ref(
            "l10n_br_esocial.mot_deslig_02"
        )
        payslip = self._rescisao(l10n_br_tipo_rescisao="culpa_reciproca")
        s2299 = self._gerar(payslip)
        self.assertTrue(s2299)
        self.assertEqual(s2299.motivo_desligamento_id.codigo, "05")
        self.assertEqual(s2299._to_esociallib_dict()["mtv_deslig"], "05")

    def test_s2299_gerado_de_cada_causa_nova(self):
        if "l10n_br_tipo_rescisao" not in self.env["hr.payslip"]._fields:
            self.skipTest("l10n_br_hr_vacation não instalado")
        if not HAS_ESOCIALLIB:
            self.skipTest("esociallib não instalada")
        esperado = {"rescisao_indireta": "17", "forca_maior": "27", "acordo": "33"}
        for tipo, codigo in esperado.items():
            payslip = self._rescisao(l10n_br_tipo_rescisao=tipo)
            s2299 = self._gerar(payslip)
            self.assertEqual(s2299.motivo_desligamento_id.codigo, codigo, tipo)
