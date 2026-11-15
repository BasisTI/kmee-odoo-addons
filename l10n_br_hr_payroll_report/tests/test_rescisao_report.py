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
from unittest.mock import patch

from lxml import etree

from odoo.addons.l10n_br_hr_payroll.tests.common import PayrollCommon
from odoo.addons.l10n_br_hr_payroll_report.models.report_rescisao import CAMPOS_VERBAS


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
        # Linha da multa só na nota informativa, nunca nas verbas.
        verbas = "".join(arvore.xpath("//tr[@class='rescisao-verba']//text()"))
        self.assertNotIn(multa.name, verbas)
        self.assertTrue(arvore.xpath("//p[@class='multa-fgts-informativa']"))
        totais = [
            _numero("".join(td.itertext()))
            for td in arvore.xpath("//tr[@class='rescisao-totals']/td[position()>1]")
        ]
        liquido = payslip.line_ids.filtered(lambda ln: ln.code == "NET").total
        self.assertAlmostEqual(totais[0] - totais[1], liquido, places=2)
        self.assertAlmostEqual(totais[2], liquido, places=2)

    # ── TG-100: TRCT e termo de quitação no modelo oficial ──────────────

    def _trct(self, payslip):
        return self.env["report.l10n_br_hr_payroll_report.report_termo_rescisao"].trct(
            payslip
        )

    def _rescisao_sem_justa_causa(self):
        payslip = self._create_rescisao_payslip()
        payslip.write(
            {
                "l10n_br_tipo_rescisao": "sem_justa_causa",
                "l10n_br_aviso_previo": "indenizado",
            }
        )
        payslip.compute_sheet()
        return payslip

    def _valor(self, trct, grupo, campo):
        return {c: v for c, _r, v, _a in trct[grupo]}[campo]

    def _linha(self, payslip, codigo):
        return sum(
            payslip.line_ids.filtered(lambda ln: ln.code == codigo).mapped("total")
        )

    def test_trct_mapeia_rubricas_para_os_campos_do_anexo(self):
        """Saldo de salário no 50, 13º no 63, férias no 65 e 66.1, terço no 68,
        aviso no 69 e INSS/IRRF nos 112.1 e 114.1."""
        payslip = self._rescisao_sem_justa_causa()
        trct = self._trct(payslip)
        esperado = {
            "50": self._linha(payslip, "SALDO_SALARIO"),
            "63": self._linha(payslip, "DECIMO_RESCISAO"),
            "65": self._linha(payslip, "FERIAS_INDENIZADAS"),
            "66.1": self._linha(payslip, "FERIAS_VENCIDAS"),
            "68": self._linha(payslip, "ADICIONAL_FERIAS_INDENIZADAS")
            + self._linha(payslip, "ADICIONAL_FERIAS_VENCIDAS"),
            "69": self._linha(payslip, "AVISO_PREVIO_INDENIZADO"),
        }
        for campo, valor in esperado.items():
            self.assertAlmostEqual(self._valor(trct, "verbas", campo), valor, places=2)
        self.assertGreater(esperado["50"], 0)
        self.assertGreater(esperado["69"], 0)
        self.assertAlmostEqual(
            self._valor(trct, "descontos", "112.1"),
            self._linha(payslip, "INSS") + 0.0,
            places=2,
        )
        self.assertAlmostEqual(
            self._valor(trct, "descontos", "114.1"),
            self._linha(payslip, "IRRF"),
            places=2,
        )

    def test_trct_nenhuma_rubrica_some_e_o_total_fecha(self):
        """Verbas + descontos dos campos = proventos e descontos do holerite, e
        bruto - deduções = líquido."""
        payslip = self._rescisao_sem_justa_causa()
        trct = self._trct(payslip)
        self.assertAlmostEqual(
            sum(v for _c, _r, v, _a in trct["verbas"]), trct["total_bruto"], places=2
        )
        self.assertAlmostEqual(
            sum(v for _c, _r, v, _a in trct["descontos"]),
            trct["total_deducoes"],
            places=2,
        )
        liquido = self._linha(payslip, "NET")
        self.assertAlmostEqual(trct["liquido"], liquido, places=2)
        self.assertAlmostEqual(
            trct["total_bruto"] - trct["total_deducoes"], liquido, places=2
        )

    def test_trct_rubrica_sem_campo_vai_para_outras_com_descricao(self):
        """Rubrica fora do mapa não some: soma em 95/115 e aparece com o nome."""
        payslip = self._rescisao_sem_justa_causa()
        modelo = self.env["report.l10n_br_hr_payroll_report.report_termo_rescisao"]
        linhas = payslip.line_ids.filtered(
            lambda ln: ln.code in ("SALDO_SALARIO", "INSS") and ln.total
        )
        verbas, outras = modelo._agrupar(linhas, {}, {}, "95")
        self.assertEqual(
            sorted(nome for nome, _v in outras), sorted(linhas.mapped("name"))
        )
        self.assertAlmostEqual(verbas["95"], sum(linhas.mapped("total")), places=2)

    def test_trct_outras_verbas_e_descontos_impressos_com_a_descricao(self):
        """Uma rubrica sem campo (devolução de INSS do 13º) sai no termo."""
        payslip = self._rescisao_sem_justa_causa()
        trct = self._trct(payslip)
        sem_campo = payslip.line_ids.filtered(
            lambda ln: ln.code
            in self.env["report.l10n_br_hr_payroll_report.report_holerite"]
            .contracheque(payslip)["proventos"]
            .mapped("code")
            and ln.code not in CAMPOS_VERBAS
        )
        self.assertEqual(
            sorted(n for n, _v in trct["outras_verbas"]),
            sorted(sem_campo.mapped("name")),
        )

    def test_trct_dados_do_contrato(self):
        """Causa, código do afastamento (mtvDeslig da TG-96), admissão, aviso
        e afastamento."""
        payslip = self._rescisao_sem_justa_causa()
        contrato = self._trct(payslip)["contrato"]
        self.assertIn("Sem Justa Causa", contrato["causa"])
        self.assertEqual(contrato["codigo_afastamento"], "02")
        self.assertEqual(contrato["admissao"], payslip.contract_id.date_start)
        self.assertEqual(contrato["afastamento"], payslip.date_to)
        self.assertEqual(contrato["aviso"], payslip.date_to)
        self.assertEqual(contrato["tipo_contrato"], "Prazo indeterminado")
        self.assertEqual(contrato["remuneracao"], 5000.0)

    def test_trct_termo_de_termino_de_contrato_e_prazo_determinado(self):
        payslip = self._create_rescisao_payslip()
        payslip.write(
            {
                "l10n_br_tipo_rescisao": "termino_contrato",
                "l10n_br_aviso_previo": "nao_aplicavel",
            }
        )
        payslip.compute_sheet()
        contrato = self._trct(payslip)["contrato"]
        self.assertEqual(contrato["tipo_contrato"], "Prazo determinado")
        self.assertEqual(contrato["codigo_afastamento"], "06")
        self.assertFalse(contrato["aviso"])

    def test_trct_justa_causa_sem_13_nem_aviso(self):
        payslip = self._create_rescisao_payslip()
        payslip.write(
            {
                "l10n_br_tipo_rescisao": "justa_causa",
                "l10n_br_aviso_previo": "nao_aplicavel",
            }
        )
        payslip.compute_sheet()
        trct = self._trct(payslip)
        self.assertEqual(trct["contrato"]["codigo_afastamento"], "01")
        self.assertEqual(self._valor(trct, "verbas", "63"), 0.0)
        self.assertEqual(self._valor(trct, "verbas", "69"), 0.0)
        self.assertAlmostEqual(
            trct["total_bruto"] - trct["total_deducoes"], trct["liquido"], places=2
        )

    def test_trct_html_traz_campos_numerados_e_termo_de_quitacao(self):
        """O PDF traz os blocos do anexo, os campos numerados e o termo de
        quitação com o líquido."""
        payslip = self._rescisao_sem_justa_causa()
        report = self.env.ref("l10n_br_hr_payroll_report.action_report_termo_rescisao")
        html = self.env["ir.actions.report"]._render_qweb_html(report.id, payslip.ids)[
            0
        ]
        arvore = etree.fromstring(html, etree.HTMLParser())
        texto = " ".join(arvore.xpath("//body//text()"))
        for trecho in (
            "IDENTIFICAÇÃO DO EMPREGADOR",
            "IDENTIFICAÇÃO DO TRABALHADOR",
            "DADOS DO CONTRATO",
            "DISCRIMINAÇÃO DAS VERBAS RESCISÓRIAS",
            "DEDUÇÕES",
            "Saldo de Salário",
            "13º Salário Proporcional",
            "Adiantamento de 13º Salário",
            "TERMO DE QUITAÇÃO",
        ):
            self.assertIn(trecho, texto)
        campos = [
            "".join(td.itertext()).strip()
            for td in arvore.xpath("//td[contains(@class, 'rescisao-campo')]")
        ]
        for campo in ("50", "63", "66.1", "69", "102", "112.1", "114.1"):
            self.assertIn(campo, campos)
        quitacao = arvore.xpath("//div[contains(@class, 'termo-quitacao')]")
        self.assertTrue(quitacao)
        liquido = self._linha(payslip, "NET")
        self.assertAlmostEqual(
            _numero(
                " ".join(
                    arvore.xpath("//div[contains(@class, 'termo-quitacao')]//strong")[
                        -1
                    ].itertext()
                )
            ),
            liquido,
            places=2,
        )

    def test_trct_mesmo_perfil_de_impressao_do_recibo(self):
        """Quem imprime o TRCT é quem imprime o recibo de férias: a ação não
        abre acesso novo (mesmos grupos)."""
        trct = self.env.ref("l10n_br_hr_payroll_report.action_report_termo_rescisao")
        recibo = self.env.ref("l10n_br_hr_payroll_report.action_report_recibo_ferias")
        self.assertEqual(trct.groups_id, recibo.groups_id)
        self.assertEqual(trct.binding_model_id, recibo.binding_model_id)

    def test_trct_rubrica_sem_campo_aparece_no_pdf_em_outras_verbas(self):
        """Sem o campo do saldo no mapa, a rubrica sai em 95 com o nome dela e
        os totais seguem fechando (nada some no termo impresso)."""
        payslip = self._rescisao_sem_justa_causa()
        saldo = payslip.line_ids.filtered(lambda ln: ln.code == "SALDO_SALARIO")
        mapa = {k: v for k, v in CAMPOS_VERBAS.items() if k != "SALDO_SALARIO"}
        with patch.dict(CAMPOS_VERBAS, clear=True):
            CAMPOS_VERBAS.update(mapa)
            trct = self._trct(payslip)
            report = self.env.ref(
                "l10n_br_hr_payroll_report.action_report_termo_rescisao"
            )
            html = self.env["ir.actions.report"]._render_qweb_html(
                report.id, payslip.ids
            )[0]
        self.assertEqual(self._valor(trct, "verbas", "50"), 0.0)
        self.assertAlmostEqual(self._valor(trct, "verbas", "95"), saldo.total, places=2)
        arvore = etree.fromstring(html, etree.HTMLParser())
        detalhe = [
            " ".join("".join(tr.itertext()).split())
            for tr in arvore.xpath("//tr[@class='rescisao-outras']")
        ]
        self.assertEqual(len(detalhe), 1)
        self.assertIn(saldo.name, detalhe[0])
        self.assertAlmostEqual(
            trct["total_bruto"] - trct["total_deducoes"], trct["liquido"], places=2
        )
