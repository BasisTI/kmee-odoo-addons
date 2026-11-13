# Copyright 2024 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""
Testes: Relatório Termo de Rescisão.

Cobertura:
  - Ação de relatório está registrada
  - Relatório renderiza sem erro
  - Conteúdo HTML contém dados esperados
"""
from datetime import date

from lxml import etree

from odoo.addons.l10n_br_hr_payroll.tests.common import PayrollCommon


def _numero(texto):
    """Converte "R$ 1.234,56" ou "$ 1,234.56" em float (último separador = decimal)."""
    limpo = "".join(c for c in texto if c.isdigit() or c in ".,")
    pos = max(limpo.rfind("."), limpo.rfind(","))
    inteiro = "".join(c for c in limpo[:pos] if c.isdigit())
    return float(f"{inteiro}.{limpo[pos + 1:]}")


class TestRescisaoReport(PayrollCommon):
    """Testes do relatório de termo de rescisão."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.structure_rescisao = cls.env.ref("l10n_br_hr_vacation.structure_rescisao")

    def _create_rescisao_payslip(self):
        """Helper: cria payslip de rescisão computado."""
        emp = self._create_employee()
        contract = self._create_contract(emp, wage=5000.00)
        payslip = self.env["hr.payslip"].create(
            {
                "name": f"Rescisão - {emp.name}",
                "employee_id": emp.id,
                "contract_id": contract.id,
                "struct_id": self.structure_rescisao.id,
                "date_from": date(2024, 3, 1),
                "date_to": date(2024, 3, 31),
            }
        )
        payslip.compute_sheet()
        return payslip

    def test_rescisao_report_action_exists(self):
        """Ação de relatório de rescisão está registrada."""
        report = self.env.ref("l10n_br_hr_payroll_report.action_report_termo_rescisao")
        self.assertEqual(report.model, "hr.payslip")
        self.assertEqual(report.report_type, "qweb-pdf")

    def test_rescisao_report_renders_html(self):
        """Relatório de rescisão renderiza HTML sem erro."""
        payslip = self._create_rescisao_payslip()
        report = self.env.ref("l10n_br_hr_payroll_report.action_report_termo_rescisao")
        html = self.env["ir.actions.report"]._render_qweb_html(report.id, payslip.ids)
        self.assertTrue(html)
        self.assertTrue(html[0])

    def test_rescisao_report_contains_title(self):
        """HTML contém título do termo de rescisão."""
        payslip = self._create_rescisao_payslip()
        report = self.env.ref("l10n_br_hr_payroll_report.action_report_termo_rescisao")
        html_content = (
            self.env["ir.actions.report"]
            ._render_qweb_html(report.id, payslip.ids)[0]
            .decode("utf-8")
        )
        self.assertIn("TERMO DE RESCISÃO", html_content.upper())
        self.assertIn(payslip.employee_id.name, html_content)

    def test_rescisao_report_multa_fgts_informativa_e_total_fecha(self):
        """TG-92: a multa do FGTS fica fora de Proventos e dos totais, e
        Proventos - Descontos = Líquido Rescisório no TRCT impresso."""
        payslip = self._create_rescisao_payslip()
        payslip.write(
            {
                "l10n_br_tipo_rescisao": "sem_justa_causa",
                "l10n_br_aviso_previo": "indenizado",
            }
        )
        payslip.compute_sheet()
        multa = payslip.line_ids.filtered(lambda ln: ln.code == "MULTA_FGTS")
        self.assertGreater(multa.total, 0.0)
        report = self.env.ref("l10n_br_hr_payroll_report.action_report_termo_rescisao")
        html = self.env["ir.actions.report"]._render_qweb_html(report.id, payslip.ids)[
            0
        ]
        arvore = etree.fromstring(html, etree.HTMLParser())
        # Linha da multa só na nota informativa, nunca na tabela de verbas.
        codigos = [
            td.text.strip()
            for td in arvore.xpath(
                "//table[@class='rescisao-table']//td[contains(@class, 'text-center')]/span"
            )
            if td.text
        ]
        self.assertNotIn("MULTA_FGTS", codigos)
        self.assertTrue(arvore.xpath("//p[@class='multa-fgts-informativa']"))
        totais = [
            _numero("".join(td.itertext()))
            for td in arvore.xpath("//tr[@class='rescisao-totals']/td[position()>1]")
        ]
        liquido = payslip.line_ids.filtered(lambda ln: ln.code == "NET").total
        self.assertAlmostEqual(totais[0] - totais[1], liquido, places=2)
