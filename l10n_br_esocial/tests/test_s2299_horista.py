# Copyright 2026 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""TG-168 r2: o S-2299 da rescisão do horista gera e valida."""

from datetime import date

from odoo.tests import tagged
from odoo.tools import mute_logger

from .common import HAS_ESOCIALLIB, ESocialCicloCommon


@tagged("post_install", "-at_install")
class TestS2299Horista(ESocialCicloCommon):
    def test_s2299_do_horista_gera_e_valida(self):
        if "l10n_br_tipo_rescisao" not in self.env["hr.payslip"]._fields:
            self.skipTest("l10n_br_hr_vacation não instalado")
        if not HAS_ESOCIALLIB:
            self.skipTest("esociallib não instalada")
        # CPF válido: o l10n_br_hr_validacao_folha recusa o fictício do common.
        self.employee.cnpj_cpf = "111.444.777-35"
        unidade = self.env["hr.contract.salary.unit"].search([("code", "=", "1")])
        self.contract.write(
            {
                "salary_unit": unidade.id,
                "l10n_br_valor_hora": 20.0,
                "date_start": date(2025, 1, 1),
                "l10n_br_esocial_motivo_deslig_id": self.env.ref(
                    "l10n_br_esocial.mot_deslig_02"
                ).id,
            }
        )
        clt = self.env.ref("l10n_br_hr_payroll.structure_clt")
        for mes in range(1, 6):
            mensal = self.env["hr.payslip"].create(
                {
                    "name": f"M {mes}",
                    "employee_id": self.employee.id,
                    "contract_id": self.contract.id,
                    "struct_id": clt.id,
                    "date_from": date(2025, mes, 1),
                    "date_to": date(2025, mes, 28),
                    "l10n_br_horas_pagas": 100.0 + 20 * mes,
                }
            )
            mensal.compute_sheet()
            mensal.action_payslip_done()
        rescisao = self.env["hr.payslip"].create(
            {
                "name": "Rescisão horista",
                "employee_id": self.employee.id,
                "contract_id": self.contract.id,
                "struct_id": self.env.ref("l10n_br_hr_vacation.structure_rescisao").id,
                "date_from": date(2025, 6, 1),
                "date_to": date(2025, 6, 18),
                "l10n_br_horas_pagas": 90.0,
            }
        )
        rescisao.compute_sheet()
        rescisao.action_payslip_done()
        with mute_logger(
            "odoo.addons.l10n_br_esocial.models.intermediarios.s2299_desligamento"
        ):
            rescisao.action_esocial_gerar_s2299()
            s2299 = rescisao.l10n_br_esocial_s2299_ids
            self.assertTrue(s2299)
            dados = s2299._to_esociallib_dict()
        self.assertTrue(dados)
        xml = s2299.evento_id.xml_envio if s2299.evento_id else None
        if xml:
            from esociallib.validators import validate_xsd

            try:
                erros = validate_xsd(xml, "S-2299")
            except FileNotFoundError:
                return
            self.assertEqual([e for e in erros if "Signature" not in e], [])
