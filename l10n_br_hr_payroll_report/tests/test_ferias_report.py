# Copyright 2024 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""
Testes: Relatório Recibo de Férias.

Cobertura:
  - Ação de relatório está registrada
  - Relatório renderiza sem erro
  - Conteúdo HTML contém dados esperados
"""
from datetime import date, datetime

from odoo.exceptions import UserError
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
        cls.modelo = cls.env["report.l10n_br_hr_payroll_report.report_recibo_ferias"]
        cls.modelo_aviso = cls.env[
            "report.l10n_br_hr_payroll_report.report_aviso_ferias"
        ]

    def _contrato(self, wage=3000.00):
        emp = self._create_employee()
        contract = self._create_contract(emp, wage=wage, date_start=date(2023, 1, 1))
        calendario = self.env["resource.calendar"].create(
            {"name": "Calendário de teste", "tz": "UTC"}
        )
        contract.resource_calendar_id = calendario
        alloc = self.env["hr.leave.allocation"].create(
            {
                "employee_id": emp.id,
                "holiday_status_id": self.leave_type_ferias.id,
                "date_from": date(2024, 1, 1),
                "date_to": date(2024, 12, 31),
            }
        )
        alloc.action_validate()
        return emp, contract, alloc

    def _slip(self, emp, contract, alloc, inicio, fim, dias, abono=0):
        slip = self.env["hr.payslip"].create(
            {
                "name": "Férias",
                "employee_id": emp.id,
                "contract_id": contract.id,
                "struct_id": self.structure_ferias.id,
                "date_from": inicio,
                "date_to": fim,
                "l10n_br_ferias_allocation_id": alloc.id if alloc else False,
                "l10n_br_dias_periodo_gozado": dias,
                "l10n_br_dias_abono": abono,
                "company_id": self.env.company.id,
            }
        )
        slip.compute_sheet()
        return slip

    def _recibo(self, abono=0, dias=20, inicio=None, fim=None):
        inicio = inicio or date(2025, 3, 3)
        fim = fim or date(2025, 3, 30)
        emp, contract, alloc = self._contrato()
        return self._slip(emp, contract, alloc, inicio, fim, dias, abono)

    def _ausencia(self, emp, inicio, fim, validar=True):
        leave = self.env["hr.leave"].create(
            {
                "employee_id": emp.id,
                "holiday_status_id": self.leave_type_ferias.id,
                "request_date_from": inicio,
                "request_date_to": fim,
            }
        )
        if validar:
            leave.action_validate()
        return leave

    def _html(self, xmlid, doc):
        report = self.env.ref(xmlid)
        return (
            self.env["ir.actions.report"]
            ._render_qweb_html(report.id, doc.ids)[0]
            .decode("utf-8")
        )

    # -- recibo -------------------------------------------------------------

    def test_periodo_aquisitivo_e_de_gozo_distintos(self):
        slip = self._recibo(dias=20, abono=10)
        dados = self.modelo.dados_ferias(slip)
        self.assertEqual(dados["aquisitivo_inicio"], date(2024, 1, 1))
        self.assertEqual(dados["aquisitivo_fim"], date(2024, 12, 31))
        self.assertEqual(dados["gozo_inicio"], date(2025, 3, 3))
        self.assertEqual(dados["gozo_fim"], date(2025, 3, 22))
        self.assertEqual(dados["dias_gozados"], 20)
        self.assertEqual(dados["pagar_ate"], date(2025, 3, 1))
        self.assertEqual(dados["dias_abono"], 10)

    def test_retorno_no_proximo_dia_de_trabalho(self):
        """Gozo que acaba no sábado: retorna na segunda, não no domingo."""
        slip = self._recibo(dias=20, abono=10)
        self.assertEqual(date(2025, 3, 22).weekday(), 5)
        self.assertEqual(self.modelo.dados_ferias(slip)["retorno"], date(2025, 3, 24))

    def test_retorno_pula_feriado_do_calendario(self):
        slip = self._recibo(dias=20, abono=10)
        feriado = self.env["resource.calendar.leaves"].create(
            {
                "name": "Feriado de teste",
                "calendar_id": slip.contract_id.resource_calendar_id.id,
                "date_from": datetime(2025, 3, 24, 0, 0, 0),
                "date_to": datetime(2025, 3, 24, 23, 59, 59),
            }
        )
        # O create desloca as horas pelo fuso do usuário; grava de novo o dia
        # inteiro em UTC, que é o fuso do calendário do teste.
        feriado.write(
            {
                "date_from": datetime(2025, 3, 24, 0, 0, 0),
                "date_to": datetime(2025, 3, 24, 23, 59, 59),
            }
        )
        calendario = slip.contract_id.resource_calendar_id
        self.assertIn(
            date(2025, 3, 24),
            self.modelo._feriados(
                calendario, slip.company_id, date(2025, 3, 22), date(2025, 4, 21)
            ),
            "feriados=%s tz=%s"
            % (
                self.env["resource.calendar.leaves"]
                .search([("calendar_id", "=", calendario.id)])
                .read(["date_from", "date_to", "resource_id", "company_id"]),
                calendario.tz,
            ),
        )
        self.assertEqual(self.modelo.dados_ferias(slip)["retorno"], date(2025, 3, 25))

    def test_abono_e_terco_do_abono(self):
        slip = self._recibo(dias=20, abono=10)
        dados = self.modelo.dados_ferias(slip)
        self.assertEqual(dados["valor_abono"], 1000.00)
        self.assertEqual(dados["terco_abono"], 333.33)
        self.assertEqual(dados["terco_ferias"], round(dados["valor_ferias"] / 3, 2))
        html = self._html("l10n_br_hr_payroll_report.action_report_recibo_ferias", slip)
        self.assertIn("Abono pecuniário:", html)
        self.assertIn("10 dias vendidos", html)

    def test_recibo_sem_venda_de_dias(self):
        slip = self._recibo(dias=30, abono=0, fim=date(2025, 4, 1))
        html = self._html("l10n_br_hr_payroll_report.action_report_recibo_ferias", slip)
        self.assertIn("não há venda de dias", html)
        self.assertRegex(html, r"Abono pecuniário:</strong>\s+não há venda")

    def test_recibo_nao_traz_o_subtotal_nem_perde_o_liquido(self):
        """O GROSS não sai nos proventos (era a coluna dobrada) e o líquido fecha."""
        slip = self._recibo(dias=20, abono=10)
        html = self._html("l10n_br_hr_payroll_report.action_report_recibo_ferias", slip)
        self.assertNotIn("Remuneração Bruta", html)
        for nome in ("Adicional de Férias", "Abono Pecuniário", "INSS"):
            self.assertIn(nome, html)
        c = self.env["report.l10n_br_hr_payroll_report.report_holerite"].contracheque(
            slip
        )
        self.assertEqual(c["liquido"], self._get_line_total(slip, "NET"))
        self.assertAlmostEqual(
            c["total_proventos"] - c["total_descontos"], c["liquido"], places=2
        )

    def test_recibo_confirmado_nao_recalcula_na_impressao(self):
        """Mensal confirmado depois, reajuste e periculosidade não mexem no quadro."""
        emp, contract, alloc = self._contrato()
        slip = self._slip(emp, contract, alloc, date(2025, 3, 3), date(2025, 3, 30), 30)
        slip.action_payslip_done()
        antes = self.modelo.dados_ferias(slip)
        self.assertEqual(antes["salario"], 3000.00)
        self.assertEqual(antes["media"], 0.0)
        self.assertEqual(antes["adicionais"], 0.0)
        mensal = self.env["hr.payslip"].create(
            {
                "name": "Mensal 01/2025",
                "employee_id": emp.id,
                "contract_id": contract.id,
                "struct_id": self.structure_clt.id,
                "date_from": date(2025, 1, 1),
                "date_to": date(2025, 1, 31),
                "l10n_br_horas_extras_50": 20.0,
                "company_id": self.env.company.id,
            }
        )
        mensal.compute_sheet()
        mensal.action_payslip_done()
        # Pré-condição: recalcular agora daria uma média; o quadro tem de ignorá-la.
        self.assertGreater(
            slip._l10n_br_media_habitual(slip._l10n_br_codes_media_habitual()), 0
        )
        contract.write({"wage": 7000.00, "l10n_br_periculosidade": True})
        depois = self.modelo.dados_ferias(slip)
        for chave in ("salario", "media", "adicionais", "remuneracao", "valor_ferias"):
            self.assertEqual(depois[chave], antes[chave], chave)
        html = self._html("l10n_br_hr_payroll_report.action_report_recibo_ferias", slip)
        # Formato do idioma do banco (3,000.00 ou 3.000,00): o que importa é o
        # salário gravado aparecer e o reajustado não.
        self.assertTrue("3,000.00" in html or "3.000,00" in html)
        self.assertNotIn("7,000.00", html)
        self.assertNotIn("7.000,00", html)

    def test_composicao_gravada_bate_com_a_rubrica(self):
        """Salário + média + adicionais, dividido por 30, é o que pagou as férias."""
        emp, contract, alloc = self._contrato()
        contract.l10n_br_periculosidade = True
        slip = self._slip(emp, contract, alloc, date(2025, 3, 3), date(2025, 3, 30), 20)
        dados = self.modelo.dados_ferias(slip)
        self.assertEqual(dados["adicionais"], 900.00)
        self.assertEqual(
            round(dados["remuneracao"] * 20 / 30, 2),
            self._get_line_total(slip, "FERIAS"),
        )

    def test_holerite_sem_a_composicao_gravada_deriva_das_linhas(self):
        """Holerite calculado antes dos campos: total pelas linhas, sem inventar parcelas."""
        slip = self._recibo(dias=20, abono=10)
        slip.write(
            {
                "l10n_br_ferias_salario": 0.0,
                "l10n_br_ferias_media": 0.0,
                "l10n_br_ferias_adicionais": 0.0,
            }
        )
        dados = self.modelo.dados_ferias(slip)
        self.assertIsNone(dados["salario"])
        self.assertEqual(dados["remuneracao"], 3000.00)
        html = self._html("l10n_br_hr_payroll_report.action_report_recibo_ferias", slip)
        self.assertIn("Composição não gravada", html)

    def test_holerite_so_de_abono_nao_tem_gozo(self):
        emp, contract, alloc = self._contrato()
        slip = self._slip(
            emp, contract, alloc, date(2025, 6, 1), date(2025, 6, 1), 0, 10
        )
        dados = self.modelo.dados_ferias(slip)
        self.assertFalse(dados["gozo_inicio"])
        self.assertFalse(dados["retorno"])
        html = self._html("l10n_br_hr_payroll_report.action_report_recibo_ferias", slip)
        self.assertIn("somente abono", html)
        self.assertNotIn("(0 dias)", html)
        self.assertEqual(dados["remuneracao"], 3000.00)

    def test_sem_alocacao_periodo_coerente_com_os_dias_pagos(self):
        """Sem alocação a regra paga 30 dias; o período mostra os mesmos 30."""
        emp, contract, _alloc = self._contrato()
        slip = self._slip(emp, contract, False, date(2025, 3, 3), date(2025, 3, 17), 0)
        dados = self.modelo.dados_ferias(slip)
        self.assertEqual(dados["dias_gozados"], 30)
        self.assertEqual(dados["gozo_fim"], date(2025, 4, 1))
        self.assertEqual(dados["valor_ferias"], 3000.00)
        html = self._html("l10n_br_hr_payroll_report.action_report_recibo_ferias", slip)
        self.assertIn("(30 dias)", html)
        self.assertIn("não informado", html)

    def test_fracao_identificada_desde_a_primeira(self):
        emp, contract, alloc = self._contrato()
        f1 = self._slip(emp, contract, alloc, date(2025, 3, 3), date(2025, 3, 16), 14)
        self.assertEqual(self.modelo._fracao(f1), (1, 1))
        f2 = self._slip(emp, contract, alloc, date(2025, 6, 2), date(2025, 6, 9), 8)
        f3 = self._slip(emp, contract, alloc, date(2025, 9, 1), date(2025, 9, 8), 8)
        self.assertEqual(self.modelo._fracao(f1), (1, 3))
        self.assertEqual(self.modelo._fracao(f2), (2, 3))
        self.assertEqual(self.modelo._fracao(f3), (3, 3))

    def test_cancelar_e_refazer_a_segunda_nao_cria_quarta_fracao(self):
        emp, contract, alloc = self._contrato()
        f1 = self._slip(emp, contract, alloc, date(2025, 3, 3), date(2025, 3, 16), 14)
        f2 = self._slip(emp, contract, alloc, date(2025, 6, 2), date(2025, 6, 9), 8)
        f3 = self._slip(emp, contract, alloc, date(2025, 9, 1), date(2025, 9, 8), 8)
        f2.action_payslip_cancel()
        # Cancelada a do meio, as outras duas são "1 de 2" e "2 de 2".
        self.assertEqual(self.modelo._fracao(f1), (1, 2))
        self.assertEqual(self.modelo._fracao(f3), (2, 2))
        # Cancelado não é fração de ninguém.
        self.assertEqual(self.modelo._fracao(f2), (0, 0))
        html = self._html("l10n_br_hr_payroll_report.action_report_recibo_ferias", f2)
        self.assertIn("HOLERITE CANCELADO", html)
        # Refeita a 2ª: volta a ser "1 de 3", "2 de 3", "3 de 3".
        f2b = self._slip(emp, contract, alloc, date(2025, 6, 2), date(2025, 6, 9), 8)
        self.assertEqual(self.modelo._fracao(f1), (1, 3))
        self.assertEqual(self.modelo._fracao(f2b), (2, 3))
        self.assertEqual(self.modelo._fracao(f3), (3, 3))

    # -- aviso a partir da ausência ----------------------------------------

    def test_aviso_parte_da_ausencia_com_abono_do_holerite(self):
        emp, contract, alloc = self._contrato()
        self._slip(emp, contract, alloc, date(2025, 3, 3), date(2025, 3, 22), 20, 10)
        leave = self._ausencia(emp, date(2025, 3, 3), date(2025, 3, 22))
        dados = self.modelo_aviso.dados_aviso(leave, data_emissao=date(2025, 2, 1))
        self.assertEqual(dados["dias"], 20)
        self.assertEqual(dados["retorno"], date(2025, 3, 24))
        self.assertEqual(dados["dias_abono"], 10)
        self.assertEqual(dados["data_minima"], date(2025, 2, 1))
        self.assertEqual(dados["antecedencia"], 30)
        self.assertFalse(dados["fora_do_prazo"])
        self.assertEqual(dados["fracao"], 1)

    def test_aviso_sem_holerite_ainda_sai(self):
        """O RH avisa antes do holerite existir: a ausência basta."""
        emp, _contract, _alloc = self._contrato()
        leave = self._ausencia(emp, date(2025, 3, 3), date(2025, 3, 22))
        dados = self.modelo_aviso.dados_aviso(leave, data_emissao=date(2025, 2, 1))
        self.assertEqual(dados["dias_abono"], 0)
        self.assertEqual(dados["dias"], 20)

    def test_data_de_emissao_gravada_na_primeira_vez(self):
        emp, _contract, _alloc = self._contrato()
        leave = self._ausencia(emp, date(2025, 3, 3), date(2025, 3, 22))
        primeira = self.modelo_aviso.dados_aviso(leave, data_emissao=date(2025, 2, 10))
        self.assertTrue(primeira["fora_do_prazo"])
        self.assertEqual(leave.l10n_br_aviso_ferias_data, date(2025, 2, 10))
        # Reimpressão em outra data: não muda a data nem o prazo.
        segunda = self.modelo_aviso.dados_aviso(leave, data_emissao=date(2025, 3, 1))
        self.assertEqual(segunda["emissao"], date(2025, 2, 10))
        self.assertEqual(segunda["antecedencia"], primeira["antecedencia"])

    def test_reimpressao_nao_acusa_atraso_que_nao_houve(self):
        emp, _contract, _alloc = self._contrato()
        leave = self._ausencia(emp, date(2025, 3, 3), date(2025, 3, 22))
        self.modelo_aviso.dados_aviso(leave, data_emissao=date(2025, 1, 20))
        reimpresso = self.modelo_aviso.dados_aviso(leave)  # hoje, bem depois
        self.assertFalse(reimpresso["fora_do_prazo"])

    def test_remarcar_a_ausencia_grava_nova_data_de_comunicacao(self):
        """Aviso de 25/10 para 29/11; remarcada para 04/12, a comunicação é de hoje."""
        emp, _contract, _alloc = self._contrato()
        leave = self._ausencia(emp, date(2025, 11, 29), date(2025, 12, 3))
        primeiro = self.modelo_aviso.dados_aviso(leave, data_emissao=date(2025, 10, 25))
        self.assertEqual(primeiro["antecedencia"], 35)
        self.assertFalse(primeiro["fora_do_prazo"])
        # Remarca: recusa, volta para a aprovar, muda as datas, aprova.
        leave.action_refuse()
        leave.action_reset_confirm()
        leave.write(
            {
                "request_date_from": date(2025, 12, 4),
                "request_date_to": date(2025, 12, 8),
            }
        )
        leave.action_validate()
        novo = self.modelo_aviso.dados_aviso(leave, data_emissao=date(2025, 11, 14))
        self.assertEqual(novo["emissao"], date(2025, 11, 14))
        self.assertEqual(novo["antecedencia"], 20)
        self.assertTrue(novo["fora_do_prazo"])
        self.assertEqual(leave.l10n_br_aviso_ferias_data, date(2025, 11, 14))
        # E a reimpressão do período novo repete a nova data.
        again = self.modelo_aviso.dados_aviso(leave, data_emissao=date(2025, 11, 20))
        self.assertEqual(again["emissao"], date(2025, 11, 14))

    def test_gerente_de_ausencias_sem_grupo_da_folha_imprime_o_aviso(self):
        emp, contract, alloc = self._contrato()
        self._slip(emp, contract, alloc, date(2025, 3, 3), date(2025, 3, 22), 20, 10)
        leave = self._ausencia(emp, date(2025, 3, 3), date(2025, 3, 22))
        gerente = self.env["res.users"].create(
            {
                "name": "Gerente de ausências",
                "login": "gerente_ausencias_tg99",
                "groups_id": [
                    (6, 0, [self.env.ref("hr_holidays.group_hr_holidays_manager").id])
                ],
            }
        )
        dados = self.modelo_aviso.with_user(gerente).dados_aviso(
            leave.with_user(gerente), data_emissao=date(2025, 2, 1)
        )
        self.assertEqual(dados["dias_abono"], 10)
        report = self.env.ref("l10n_br_hr_payroll_report.action_report_aviso_ferias")
        html = (
            self.env["ir.actions.report"]
            .with_user(gerente)
            ._render_qweb_html(report.id, leave.ids)[0]
            .decode("utf-8")
        )
        self.assertIn("AVISO DE FÉRIAS", html)

    def test_aviso_fora_do_prazo_alerta_e_nao_bloqueia(self):
        emp, _contract, _alloc = self._contrato()
        leave = self._ausencia(emp, date(2025, 3, 3), date(2025, 3, 22))
        dados = self.modelo_aviso.dados_aviso(leave, data_emissao=date(2025, 2, 2))
        self.assertEqual(dados["antecedencia"], 29)
        self.assertTrue(dados["fora_do_prazo"])

    def test_aviso_renderiza_pela_acao_da_ausencia(self):
        emp, contract, alloc = self._contrato()
        self._slip(emp, contract, alloc, date(2025, 3, 3), date(2025, 3, 22), 20, 10)
        leave = self._ausencia(emp, date(2025, 3, 3), date(2025, 3, 22))
        html = self._html("l10n_br_hr_payroll_report.action_report_aviso_ferias", leave)
        self.assertIn("AVISO DE FÉRIAS", html)
        self.assertIn(emp.name, html)
        self.assertIn("20 dias corridos", html)
        self.assertIn("10 dias em abono", html)
        self.assertIn("Ciente do empregado", html)
        self.assertIn("art. 135", html)
        self.assertIn("ATENÇÃO", html)  # emitido hoje para férias em 2025

    def test_aviso_so_para_ausencia_de_ferias_aprovada(self):
        emp, _contract, _alloc = self._contrato()
        rascunho = self._ausencia(
            emp, date(2025, 3, 3), date(2025, 3, 22), validar=False
        )
        with self.assertRaises(UserError):
            self.modelo_aviso.dados_aviso(rascunho)

    def test_acao_do_aviso_e_da_ausencia_e_nao_do_holerite(self):
        report = self.env.ref("l10n_br_hr_payroll_report.action_report_aviso_ferias")
        self.assertEqual(report.model, "hr.leave")
        self.assertEqual(report.binding_type, "report")
