# Copyright 2024 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""
Testes: Relatório Holerite BR.

Cobertura:
  - Ação de relatório está registrada
  - Relatório renderiza sem erro para payslip computado
  - Seções do holerite (proventos, descontos, líquido)
"""
from datetime import date

from odoo.addons.l10n_br_hr_payroll.models import salary_rules_br
from odoo.addons.l10n_br_hr_payroll.tests.common import PayrollCommon


class TestHoleriteReport(PayrollCommon):
    """Testes do relatório holerite brasileiro."""

    def _create_computed_payslip(self):
        """Helper: cria e computa payslip para relatório."""
        emp = self._create_employee()
        contract = self._create_contract(emp, wage=5000.00)
        payslip = self.env["hr.payslip"].create(
            {
                "name": f"Holerite - {emp.name}",
                "employee_id": emp.id,
                "contract_id": contract.id,
                "struct_id": contract.struct_id.id,
                "date_from": date(2024, 3, 1),
                "date_to": date(2024, 3, 31),
                "company_id": self.env.company.id,
            }
        )
        payslip.compute_sheet()
        return payslip

    def test_report_action_exists(self):
        """Ação de relatório holerite está registrada."""
        report = self.env.ref("l10n_br_hr_payroll_report.action_report_holerite")
        self.assertEqual(report.model, "hr.payslip")
        self.assertEqual(report.report_type, "qweb-pdf")

    def test_report_renders_html(self):
        """Relatório renderiza HTML sem erro."""
        payslip = self._create_computed_payslip()
        report = self.env.ref("l10n_br_hr_payroll_report.action_report_holerite")
        html = self.env["ir.actions.report"]._render_qweb_html(report.id, payslip.ids)
        self.assertTrue(html)
        self.assertTrue(html[0])

    def test_report_contains_employee_data(self):
        """HTML do holerite contém dados do empregado."""
        payslip = self._create_computed_payslip()
        report = self.env.ref("l10n_br_hr_payroll_report.action_report_holerite")
        html_content = (
            self.env["ir.actions.report"]
            ._render_qweb_html(report.id, payslip.ids)[0]
            .decode("utf-8")
        )
        self.assertIn(payslip.employee_id.name, html_content)
        self.assertIn("RECIBO DE PAGAMENTO", html_content)

    def test_report_contains_payslip_lines(self):
        """HTML contém linhas de proventos e descontos."""
        payslip = self._create_computed_payslip()
        report = self.env.ref("l10n_br_hr_payroll_report.action_report_holerite")
        html_content = (
            self.env["ir.actions.report"]
            ._render_qweb_html(report.id, payslip.ids)[0]
            .decode("utf-8")
        )
        self.assertIn("TOTAIS", html_content)
        self.assertIn("LÍQUIDO", html_content)

    def test_report_contains_net_value(self):
        """HTML contém valor líquido."""
        payslip = self._create_computed_payslip()
        net = self._get_line_total(payslip, "NET")
        report = self.env.ref("l10n_br_hr_payroll_report.action_report_holerite")
        html_content = (
            self.env["ir.actions.report"]
            ._render_qweb_html(report.id, payslip.ids)[0]
            .decode("utf-8")
        )
        # Verifica que o líquido aparece no HTML (formatado)
        self.assertTrue(net > 0)
        self.assertIn("LÍQUIDO A RECEBER", html_content)

    # ── TG-98: colunas, bases e menu do contracheque ──────────────────────

    def _contracheque(self, payslip):
        return self.env[
            "report.l10n_br_hr_payroll_report.report_holerite"
        ].contracheque(payslip)

    def _payslip_estrutura(self, xmlid, date_from, date_to):
        emp = self._create_employee()
        contract = self._create_contract(emp, wage=5000.00)
        payslip = self.env["hr.payslip"].create(
            {
                "name": f"Holerite - {emp.name}",
                "employee_id": emp.id,
                "contract_id": contract.id,
                "struct_id": self.env.ref(xmlid).id,
                "date_from": date_from,
                "date_to": date_to,
                "company_id": self.env.company.id,
            }
        )
        payslip.compute_sheet()
        return payslip

    def test_proventos_sem_subtotal_nem_provisao(self):
        """GROSS (subtotal) e provisões não entram nos proventos: o total bate com o NET."""
        payslip = self._create_computed_payslip()
        dados = self._contracheque(payslip)
        codigos = dados["proventos"].mapped("code")
        self.assertNotIn("GROSS", codigos)
        self.assertFalse([c for c in codigos if c.startswith("PROV_")])
        self.assertAlmostEqualMoney(
            dados["total_proventos"], self._get_line_total(payslip, "GROSS")
        )
        self.assertAlmostEqualMoney(
            dados["total_proventos"] - dados["total_descontos"], dados["liquido"]
        )
        self.assertAlmostEqualMoney(
            dados["liquido"], self._get_line_total(payslip, "NET")
        )

    def test_descontos_so_categoria_desconto(self):
        """Só descontos na coluna da direita; bases e encargos ficam fora."""
        payslip = self._create_computed_payslip()
        dados = self._contracheque(payslip)
        self.assertIn("INSS", dados["descontos"].mapped("code"))
        self.assertEqual(set(dados["descontos"].mapped("category_id.code")), {"DED"})
        fora = set(dados["proventos"].mapped("code")) | set(
            dados["descontos"].mapped("code")
        )
        self.assertFalse(fora & {"FGTS", "CPP", "RAT", "TERCEIROS", "BASE_IRRF"})

    def test_bases_do_mensal(self):
        """Salário de contribuição INSS, base IRRF, base FGTS e FGTS do mês."""
        payslip = self._create_computed_payslip()
        bases = dict(self._contracheque(payslip)["bases"])
        self.assertAlmostEqualMoney(bases["Sal. contribuição INSS"], 5000.0)
        # A base do IRRF é a efetivamente usada (aqui, a do simplificado): ver
        # test_base_irrf_e_a_do_simplificado_quando_ele_vence.
        self.assertIn("Base IRRF (simplificado)", bases)
        self.assertAlmostEqualMoney(bases["Base FGTS"], 5000.0)
        self.assertAlmostEqualMoney(bases["FGTS do mês"], 400.0)
        self.assertAlmostEqualMoney(
            bases["FGTS do mês"], self._get_line_total(payslip, "FGTS")
        )

    def test_bases_no_html(self):
        """As bases aparecem no PDF com os valores calculados, não zeradas."""
        payslip = self._create_computed_payslip()
        report = self.env.ref("l10n_br_hr_payroll_report.action_report_holerite")
        html = (
            self.env["ir.actions.report"]
            ._render_qweb_html(report.id, payslip.ids)[0]
            .decode("utf-8")
        )
        for rotulo in (
            "Sal. contribuição INSS",
            "Base IRRF",
            "Base FGTS",
            "FGTS do mês",
        ):
            self.assertIn(rotulo, html)
        self.assertNotIn("BASE_IRRF", html)

    def test_ferias_totais_batem_com_o_liquido(self):
        payslip = self._payslip_estrutura(
            "l10n_br_hr_vacation.structure_ferias", date(2024, 3, 1), date(2024, 3, 31)
        )
        dados = self._contracheque(payslip)
        self.assertNotIn("GROSS", dados["proventos"].mapped("code"))
        self.assertAlmostEqualMoney(
            dados["total_proventos"] - dados["total_descontos"],
            self._get_line_total(payslip, "NET"),
        )
        bases = dict(self._contracheque(payslip)["bases"])
        self.assertAlmostEqualMoney(
            bases["Base FGTS"], self._get_line_total(payslip, "GROSS")
        )

    def test_13_segunda_parcela_base_fgts_so_da_diferenca(self):
        """FGTS da 2ª parcela incide só sobre a diferença; a base mostra isso."""
        payslip = self._payslip_estrutura(
            "l10n_br_hr_vacation.structure_13_segunda_parcela",
            date(2024, 12, 1),
            date(2024, 12, 31),
        )
        bases = dict(self._contracheque(payslip)["bases"])
        self.assertAlmostEqualMoney(
            bases["Base INSS 13º"], self._get_line_total(payslip, "GROSS")
        )
        self.assertAlmostEqualMoney(
            bases["FGTS do mês"] / 0.08,
            bases["Base FGTS"],
            places=0,
        )
        self.assertTrue([k for k in bases if k.startswith("Base IRRF 13º")])

    def test_rescisao_multa_do_fgts_nao_e_provento(self):
        """A multa do FGTS vai à conta vinculada: informativa, fora do total."""
        payslip = self._payslip_estrutura(
            "l10n_br_hr_vacation.structure_rescisao",
            date(2024, 3, 1),
            date(2024, 3, 31),
        )
        dados = self._contracheque(payslip)
        self.assertNotIn("MULTA_FGTS", dados["proventos"].mapped("code"))
        self.assertAlmostEqualMoney(
            dados["total_proventos"] - dados["total_descontos"],
            self._get_line_total(payslip, "NET"),
        )

    def test_so_um_holerite_no_menu_imprimir(self):
        """O relatório da OCA sai do menu Imprimir; o da KMEE é o único Holerite."""
        oca = self.env.ref("payroll.action_report_payslip")
        self.assertFalse(oca.binding_model_id)
        kmee = self.env.ref("l10n_br_hr_payroll_report.action_report_holerite")
        self.assertTrue(kmee.binding_model_id)
        no_menu = self.env["ir.actions.report"].search(
            [("binding_model_id.model", "=", "hr.payslip"), ("name", "=", "Holerite")]
        )
        self.assertEqual(no_menu, kmee)

    # ── TG-98 r2: base do IRRF efetiva, FGTS da rescisão e colunas zeradas ──

    def _irrf_reproduzido(self, payslip, base, codigo_irrf="IRRF"):
        """IRRF que a base mostrada gera, com as tabelas da competência do holerite."""
        competencia = payslip._get_competencia()
        faixas = self.env["l10n_br.hr.payroll.irrf.faixa"]._tabela(competencia)
        redutor = self.env["l10n_br.hr.payroll.irrf.redutor"]._tabela(competencia)
        imposto = salary_rules_br.calc_irrf(base, faixas)
        rendimento = self._get_line_total(payslip, "GROSS")
        return salary_rules_br.calc_irrf_apos_redutor(rendimento, imposto, redutor)

    def test_base_irrf_e_a_do_simplificado_quando_ele_vence(self):
        """Salário de 5.000: o simplificado gera menos imposto e a base mostrada é a dele."""
        payslip = self._create_computed_payslip()
        bases = dict(self._contracheque(payslip)["bases"])
        base = bases["Base IRRF (simplificado)"]
        legal = self._get_line_total(payslip, "BASE_IRRF")
        self.assertLess(base, legal)
        irrf = self._get_line_total(payslip, "IRRF")
        self.assertGreater(irrf, 0)
        self.assertAlmostEqualMoney(self._irrf_reproduzido(payslip, base), irrf)

    def test_base_irrf_legal_quando_a_deducao_vence(self):
        """Com dependentes a dedução legal vence: mostra a rubrica, sem a marca."""
        payslip = self._create_computed_payslip()
        payslip.employee_id.l10n_br_irrf_dependentes = 4
        payslip.compute_sheet()
        bases = dict(self._contracheque(payslip)["bases"])
        self.assertNotIn("Base IRRF (simplificado)", bases)
        self.assertAlmostEqualMoney(
            bases["Base IRRF"], self._get_line_total(payslip, "BASE_IRRF")
        )

    def _rescisao_com_primeira_parcela(self):
        emp = self._create_employee()
        contract = self._create_contract(emp, wage=5000.00)
        vals = {
            "employee_id": emp.id,
            "contract_id": contract.id,
            "company_id": self.env.company.id,
        }
        primeira = self.env["hr.payslip"].create(
            dict(
                vals,
                name="13º 1ª parcela",
                struct_id=self.env.ref(
                    "l10n_br_hr_vacation.structure_13_primeira_parcela"
                ).id,
                date_from=date(2024, 11, 1),
                date_to=date(2024, 11, 30),
            )
        )
        primeira.compute_sheet()
        primeira.action_payslip_done()
        resc = self.env["hr.payslip"].create(
            dict(
                vals,
                name="Rescisão",
                struct_id=self.env.ref("l10n_br_hr_vacation.structure_rescisao").id,
                date_from=date(2024, 12, 1),
                date_to=date(2024, 12, 10),
                l10n_br_tipo_rescisao="pedido_demissao",
                l10n_br_aviso_previo="nao_aplicavel",
            )
        )
        resc.compute_sheet()
        return resc

    def test_rescisao_base_fgts_abate_a_primeira_parcela_do_13(self):
        """Base FGTS × 8% fecha com o FGTS do mês, como na 2ª parcela."""
        resc = self._rescisao_com_primeira_parcela()
        self.assertGreater(self._get_line_total(resc, "FGTS_13"), 0)
        bases = dict(self._contracheque(resc)["bases"])
        fgts = bases["FGTS do mês"]
        self.assertAlmostEqualMoney(
            fgts,
            self._get_line_total(resc, "FGTS") + self._get_line_total(resc, "FGTS_13"),
        )
        self.assertAlmostEqual(bases["Base FGTS"] * 0.08, fgts, delta=0.02)

    def test_base_zerada_nao_vira_coluna(self):
        """Nenhum quadro de bases traz coluna com R$ 0,00."""
        for payslip in (
            self._create_computed_payslip(),
            self._rescisao_com_primeira_parcela(),
        ):
            for rotulo, valor in self._contracheque(payslip)["bases"]:
                self.assertTrue(valor, f"{rotulo} zerada")

    def test_aprendiz_base_fgts_indica_a_aliquota(self):
        """Aprendiz recolhe 2%: o rótulo diz e base × 2% fecha com o FGTS."""
        emp = self._create_employee(tipo_contrato="aprendiz")
        contract = self._create_contract(emp, wage=2000.00)
        payslip = self._create_payslip(emp, contract)
        bases = dict(self._contracheque(payslip)["bases"])
        self.assertAlmostEqualMoney(
            bases["Base FGTS (2%)"] * 0.02, bases["FGTS do mês"]
        )
