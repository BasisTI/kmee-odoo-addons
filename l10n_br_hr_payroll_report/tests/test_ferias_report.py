# Copyright 2024 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""
Testes: Relatório Recibo de Férias.

Cobertura:
  - Ação de relatório está registrada
  - Relatório renderiza sem erro
  - Conteúdo HTML contém dados esperados
"""
from datetime import date

from odoo.tests import tagged

from odoo.addons.l10n_br_hr_payroll.tests.common import PayrollCommon


class TestFeriasReport(PayrollCommon):
    """Testes do relatório de recibo de férias."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.structure_ferias = cls.env.ref("l10n_br_hr_vacation.structure_ferias")

    def _create_ferias_payslip(self):
        """Helper: cria payslip de férias computado."""
        emp = self._create_employee()
        contract = self._create_contract(emp, wage=5000.00)
        payslip = self.env["hr.payslip"].create(
            {
                "name": f"Férias - {emp.name}",
                "employee_id": emp.id,
                "contract_id": contract.id,
                "struct_id": self.structure_ferias.id,
                "date_from": date(2024, 3, 1),
                "date_to": date(2024, 3, 30),
            }
        )
        payslip.compute_sheet()
        return payslip

    def test_ferias_report_action_exists(self):
        """Ação de relatório de férias está registrada."""
        report = self.env.ref("l10n_br_hr_payroll_report.action_report_recibo_ferias")
        self.assertEqual(report.model, "hr.payslip")
        self.assertEqual(report.report_type, "qweb-pdf")

    def test_ferias_report_renders_html(self):
        """Relatório de férias renderiza HTML sem erro."""
        payslip = self._create_ferias_payslip()
        report = self.env.ref("l10n_br_hr_payroll_report.action_report_recibo_ferias")
        html = self.env["ir.actions.report"]._render_qweb_html(report.id, payslip.ids)
        self.assertTrue(html)
        self.assertTrue(html[0])

    def test_ferias_report_contains_title(self):
        """HTML contém título de recibo de férias."""
        payslip = self._create_ferias_payslip()
        report = self.env.ref("l10n_br_hr_payroll_report.action_report_recibo_ferias")
        html_content = (
            self.env["ir.actions.report"]
            ._render_qweb_html(report.id, payslip.ids)[0]
            .decode("utf-8")
        )
        self.assertIn("RECIBO DE FÉRIAS", html_content)
        self.assertIn(payslip.employee_id.name, html_content)


@tagged("post_install", "-at_install")
class TestReciboAvisoFerias(PayrollCommon):
    """Recibo com período, abono, terço e médias; aviso do art. 135 da CLT."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.structure_ferias = cls.env.ref("l10n_br_hr_vacation.structure_ferias")
        cls.leave_type_ferias = cls.env.ref("l10n_br_hr_vacation.leave_type_ferias")

    def _recibo(self, abono=0, dias=20, inicio=None, fim=None):
        emp = self._create_employee()
        contract = self._create_contract(emp, wage=3000.00, date_start=date(2023, 1, 1))
        alloc = self.env["hr.leave.allocation"].create(
            {
                "employee_id": emp.id,
                "holiday_status_id": self.leave_type_ferias.id,
                "date_from": date(2023, 1, 1),
                "date_to": date(2023, 12, 31),
            }
        )
        alloc.action_validate()
        slip = self.env["hr.payslip"].create(
            {
                "name": "Férias",
                "employee_id": emp.id,
                "contract_id": contract.id,
                "struct_id": self.structure_ferias.id,
                "date_from": inicio or date(2025, 3, 3),
                "date_to": fim or date(2025, 3, 30),
                "l10n_br_ferias_allocation_id": alloc.id,
                "l10n_br_dias_periodo_gozado": dias,
                "l10n_br_dias_abono": abono,
                "company_id": self.env.company.id,
            }
        )
        slip.compute_sheet()
        return slip

    def _html(self, xmlid, slip):
        report = self.env.ref(xmlid)
        return (
            self.env["ir.actions.report"]
            ._render_qweb_html(report.id, slip.ids)[0]
            .decode("utf-8")
        )

    def test_periodo_aquisitivo_e_de_gozo_distintos(self):
        """O aquisitivo é o da alocação; o gozo, o do recibo (antes eram iguais)."""
        slip = self._recibo(dias=20, abono=10)
        dados = self.env[
            "report.l10n_br_hr_payroll_report.report_recibo_ferias"
        ].dados_ferias(slip)
        self.assertEqual(dados["aquisitivo_inicio"], date(2023, 1, 1))
        self.assertEqual(dados["aquisitivo_fim"], date(2023, 12, 31))
        self.assertEqual(dados["gozo_inicio"], date(2025, 3, 3))
        self.assertEqual(dados["gozo_fim"], date(2025, 3, 22))
        self.assertEqual(dados["retorno"], date(2025, 3, 23))
        self.assertEqual(dados["pagar_ate"], date(2025, 3, 1))
        self.assertEqual(dados["dias_abono"], 10)

    def test_abono_e_terco_do_abono(self):
        slip = self._recibo(dias=20, abono=10)
        dados = self.env[
            "report.l10n_br_hr_payroll_report.report_recibo_ferias"
        ].dados_ferias(slip)
        self.assertEqual(dados["valor_abono"], 1000.00)
        self.assertEqual(dados["terco_abono"], 333.33)
        self.assertEqual(dados["terco_ferias"], round(dados["valor_ferias"] / 3, 2))
        html = self._html("l10n_br_hr_payroll_report.action_report_recibo_ferias", slip)
        self.assertIn("Abono pecuniário", html)
        self.assertIn("10 dias vendidos", html)
        self.assertIn("Retorno ao trabalho", html)

    def test_recibo_sem_abono_e_sem_venda(self):
        slip = self._recibo(dias=30, abono=0, fim=date(2025, 4, 1))
        html = self._html("l10n_br_hr_payroll_report.action_report_recibo_ferias", slip)
        self.assertIn("não há venda de dias", html)

    def test_recibo_descontos_e_liquido_nas_colunas(self):
        slip = self._recibo(dias=20, abono=10)
        c = self.env["report.l10n_br_hr_payroll_report.report_holerite"].contracheque(
            slip
        )
        codigos = set(c["proventos"].mapped("code"))
        self.assertTrue({"FERIAS", "ADICIONAL_FERIAS", "ABONO_PECUNIARIO"} <= codigos)
        self.assertNotIn("GROSS", codigos)
        self.assertIn("INSS", set(c["descontos"].mapped("code")))
        self.assertEqual(c["liquido"], self._get_line_total(slip, "NET"))
        self.assertAlmostEqual(
            c["total_proventos"] - c["total_descontos"], c["liquido"], places=2
        )

    def test_composicao_da_remuneracao(self):
        slip = self._recibo()
        dados = self.env[
            "report.l10n_br_hr_payroll_report.report_recibo_ferias"
        ].dados_ferias(slip)
        self.assertEqual(dados["salario"], 3000.00)
        self.assertEqual(
            dados["remuneracao"],
            dados["salario"] + dados["media"] + dados["adicionais"],
        )

    def test_fracionamento_numera_os_periodos(self):
        slip = self._recibo(dias=14, fim=date(2025, 3, 30))
        segunda = slip.copy(
            {
                "date_from": date(2025, 6, 2),
                "date_to": date(2025, 6, 30),
                "l10n_br_dias_periodo_gozado": 10,
                "l10n_br_dias_abono": 0,
            }
        )
        modelo = self.env["report.l10n_br_hr_payroll_report.report_recibo_ferias"]
        self.assertEqual(modelo.dados_ferias(slip)["fracao"], 1)
        self.assertEqual(modelo.dados_ferias(segunda)["fracao"], 2)
        self.assertEqual(modelo.dados_ferias(segunda)["fracoes"], 2)

    def test_aviso_dentro_do_prazo(self):
        slip = self._recibo()
        modelo = self.env["report.l10n_br_hr_payroll_report.report_aviso_ferias"]
        dados = modelo.dados_aviso(slip, data_emissao=date(2025, 2, 1))
        self.assertEqual(dados["data_minima"], date(2025, 2, 1))
        self.assertEqual(dados["antecedencia"], 30)
        self.assertFalse(dados["fora_do_prazo"])

    def test_aviso_com_menos_de_30_dias_avisa_e_nao_bloqueia(self):
        slip = self._recibo()
        modelo = self.env["report.l10n_br_hr_payroll_report.report_aviso_ferias"]
        dados = modelo.dados_aviso(slip, data_emissao=date(2025, 2, 2))
        self.assertEqual(dados["antecedencia"], 29)
        self.assertTrue(dados["fora_do_prazo"])

    def test_aviso_renderiza_com_periodo_e_ciencia(self):
        slip = self._recibo(dias=20, abono=10)
        html = self._html("l10n_br_hr_payroll_report.action_report_aviso_ferias", slip)
        self.assertIn("AVISO DE FÉRIAS", html)
        self.assertIn(slip.employee_id.name, html)
        self.assertIn("20 dias corridos", html)
        self.assertIn("Ciente do empregado", html)
        self.assertIn("art. 135", html)
        # Emitido hoje para férias em 2025: já está fora do prazo.
        self.assertIn("ATENÇÃO", html)

    def test_aviso_na_lista_de_impressao(self):
        report = self.env.ref("l10n_br_hr_payroll_report.action_report_aviso_ferias")
        self.assertEqual(report.model, "hr.payslip")
        self.assertEqual(report.binding_type, "report")
