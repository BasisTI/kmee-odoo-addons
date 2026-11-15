# Copyright 2024 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""
Testes: Relatório Termo de Rescisão.

Cobertura:
  - Ação de relatório está registrada
  - Relatório renderiza sem erro
  - Conteúdo HTML contém dados esperados
"""
from datetime import date, timedelta
from unittest.mock import patch

from lxml import etree

from odoo.exceptions import UserError

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
        verbas, outras = modelo._agrupar(linhas, {}, "95")
        self.assertEqual(
            sorted(nome for _s, nome, _v in outras), sorted(linhas.mapped("name"))
        )
        self.assertEqual([s for s, _n, _v in outras], ["95.1", "95.2"])
        self.assertAlmostEqual(verbas["95"], sum(linhas.mapped("total")), places=2)

    def test_trct_dados_do_contrato(self):
        """Causa, código do afastamento (quadro dos campos 22 e 27), admissão, aviso
        e afastamento."""
        payslip = self._rescisao_sem_justa_causa()
        contrato = self._trct(payslip)["contrato"]
        self.assertEqual(contrato["causa"], "Dispensa sem justa causa, pelo empregador")
        self.assertEqual(contrato["codigo_afastamento"], "SJ2")
        self.assertEqual(contrato["admissao"], payslip.contract_id.date_start)
        self.assertEqual(contrato["afastamento"], payslip.date_to)
        self.assertEqual(contrato["aviso"], payslip.date_to)
        self.assertEqual(contrato["tipo_contrato"], "Prazo indeterminado")
        self.assertEqual(contrato["remuneracao"], 5000.0)

    def test_trct_campo_25_usa_a_data_do_aviso_informada(self):
        """TG-137: a data de concessão informada na rescisão (a do ``dtAvPrv`` do
        S-2299) vai ao campo 25; sem ela, vale a fórmula."""
        payslip = self._rescisao_sem_justa_causa()
        self.assertEqual(self._trct(payslip)["contrato"]["aviso"], payslip.date_to)
        data = payslip.date_from - timedelta(days=15)
        payslip.l10n_br_data_aviso_previo = data
        self.assertEqual(self._trct(payslip)["contrato"]["aviso"], data)

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
        self.assertEqual(contrato["codigo_afastamento"], "PD0")
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
        self.assertEqual(trct["contrato"]["codigo_afastamento"], "JC2")
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
        self.assertIn("95.1", detalhe[0])
        self.assertIn(saldo.name, detalhe[0])
        self.assertAlmostEqual(
            trct["total_bruto"] - trct["total_deducoes"], trct["liquido"], places=2
        )

    def test_trct_codigos_do_quadro_campos_22_e_27(self):
        """Cada causa da TG-96 imprime o código do quadro da Portaria MTE
        2.685/2011 (1.057/2012); o acordo do art. 484-A, sem código no
        quadro, imprime o texto e nunca um código inventado."""
        esperado = {
            "sem_justa_causa": "SJ2",
            "justa_causa": "JC2",
            "antecipado_empregador": "RA2",
            "antecipado_empregado": "RA1",
            "pedido_demissao": "SJ1",
            "termino_contrato": "PD0",
            "rescisao_indireta": "RI2",
            "culpa_reciproca": "CR0",
            "forca_maior": "FM0",
            "acordo": "Acordo art. 484-A",
        }
        tipos = {
            t
            for t, _n in self.env["hr.payslip"]
            ._fields["l10n_br_tipo_rescisao"]
            .selection
        }
        self.assertEqual(tipos, set(esperado))
        payslip = self._create_rescisao_payslip()
        for tipo, codigo in esperado.items():
            payslip.write(
                {
                    "l10n_br_tipo_rescisao": tipo,
                    "l10n_br_data_termo_contrato": date(2024, 6, 30),
                }
            )
            self.assertEqual(
                self._trct(payslip)["contrato"]["codigo_afastamento"], codigo
            )

    def test_trct_aviso_trabalhado_do_pedido_de_demissao_e_de_30_dias(self):
        """O aviso do empregado é de 30 dias (sem os 3 dias por ano da Lei
        12.506): o aviso começa 29 dias antes do afastamento. A dispensa sem
        justa causa do mesmo contrato segue com o aviso proporcional."""
        payslip = self._create_rescisao_payslip()
        payslip.write(
            {
                "date_from": date(2026, 11, 1),
                "date_to": date(2026, 11, 20),
                "l10n_br_tipo_rescisao": "pedido_demissao",
                "l10n_br_aviso_previo": "trabalhado",
            }
        )
        payslip.contract_id.date_start = date(2023, 3, 1)
        self.assertEqual(self._trct(payslip)["contrato"]["aviso"], date(2026, 10, 22))
        payslip.l10n_br_tipo_rescisao = "sem_justa_causa"
        self.assertEqual(self._trct(payslip)["contrato"]["aviso"], date(2026, 10, 13))

    def test_trct_rodape_do_art_487_par_2(self):
        payslip = self._rescisao_sem_justa_causa()
        report = self.env.ref("l10n_br_hr_payroll_report.action_report_termo_rescisao")
        html = self.env["ir.actions.report"]._render_qweb_html(report.id, payslip.ids)[
            0
        ]
        texto = " ".join(
            " ".join(
                etree.fromstring(html, etree.HTMLParser()).xpath("//body//text()")
            ).split()
        )
        self.assertIn(
            "A falta de aviso prévio por parte do empregado dá ao empregador o "
            "direito de descontar os salários correspondentes ao prazo respectivo",
            texto,
        )
        self.assertNotIn("É vedado ao empregador", texto)

    def test_trct_campos_04_08_09_13_e_categoria_no_html(self):
        payslip = self._rescisao_sem_justa_causa()
        report = self.env.ref("l10n_br_hr_payroll_report.action_report_termo_rescisao")
        html = self.env["ir.actions.report"]._render_qweb_html(report.id, payslip.ids)[
            0
        ]
        texto = " ".join(
            etree.fromstring(html, etree.HTMLParser()).xpath("//body//text()")
        )
        for rotulo in (
            "04 Bairro",
            "08 CNAE",
            "09 CNPJ/CEI Tomador/Obra",
            "13 Bairro",
            "30 Categoria do trabalhador",
        ):
            self.assertIn(rotulo, texto)
        self.assertEqual(
            self._trct(payslip)["contrato"]["categoria"], "Empregado - Geral"
        )

    def test_trct_ferias_vencidas_com_periodo_aquisitivo(self):
        """66.1 traz o período aquisitivo da alocação vencida e não gozada."""
        emp = self._create_employee("Vencidas")
        contract = self._create_contract(emp, date_start=date(2022, 1, 1))
        tipo = self.env.ref("l10n_br_hr_vacation.leave_type_ferias")
        aloc = self.env["hr.leave.allocation"].create(
            {
                "name": "Aquisitivo 2023",
                "employee_id": emp.id,
                "holiday_status_id": tipo.id,
                "allocation_type": "regular",
                "date_from": date(2023, 1, 1),
                "date_to": date(2023, 12, 31),
            }
        )
        aloc.sudo().action_validate()
        payslip = self.env["hr.payslip"].create(
            {
                "name": "Rescisão vencidas",
                "employee_id": emp.id,
                "contract_id": contract.id,
                "struct_id": self.structure_rescisao.id,
                "date_from": date(2026, 3, 1),
                "date_to": date(2026, 3, 31),
                "l10n_br_tipo_rescisao": "sem_justa_causa",
                "l10n_br_aviso_previo": "indenizado",
            }
        )
        payslip.compute_sheet()
        campos = {c: (v, d) for c, _r, v, d in self._trct(payslip)["verbas"]}
        self.assertGreater(campos["66.1"][0], 0)
        self.assertEqual(campos["66.1"][1], "01/01/2023 a 31/12/2023")

    def test_trct_excesso_do_13_vai_para_95_e_115_com_subitens(self):
        """TG-141: 2ª parcela confirmada acima do devido. A devolução de INSS
        sai em 95.n e o desconto do excesso em 115.n, com o nome, e os totais
        fecham no termo impresso."""
        emp = self._create_employee("Excesso 13")
        contract = self._create_contract(emp, wage=3000.0, date_start=date(2020, 1, 1))
        segunda = self.env["hr.payslip"].create(
            {
                "name": "13º 2ª",
                "employee_id": emp.id,
                "contract_id": contract.id,
                "struct_id": self.env.ref(
                    "l10n_br_hr_vacation.structure_13_segunda_parcela"
                ).id,
                "date_from": date(2026, 12, 1),
                "date_to": date(2026, 12, 20),
            }
        )
        segunda.compute_sheet()
        segunda.action_payslip_done()
        payslip = self.env["hr.payslip"].create(
            {
                "name": "Rescisão excesso",
                "employee_id": emp.id,
                "contract_id": contract.id,
                "struct_id": self.structure_rescisao.id,
                "date_from": date(2026, 12, 1),
                "date_to": date(2026, 12, 10),
                "l10n_br_tipo_rescisao": "pedido_demissao",
                "l10n_br_aviso_previo": "nao_aplicavel",
            }
        )
        payslip.compute_sheet()
        trct = self._trct(payslip)
        excesso = payslip.line_ids.filtered(lambda ln: ln.code == "DESCONTO_13_EXCESSO")
        devolucao = payslip.line_ids.filtered(lambda ln: ln.code == "DEVOLUCAO_INSS_13")
        self.assertGreater(excesso.total, 0)
        self.assertGreater(devolucao.total, 0)
        self.assertIn(
            ("115.1", excesso.name, excesso.total),
            [(s, n, round(v, 2)) for s, n, v in trct["outros_descontos"]],
        )
        self.assertTrue(
            [s for s, n, _v in trct["outras_verbas"] if n == devolucao.name]
        )
        self.assertAlmostEqual(
            trct["total_bruto"] - trct["total_deducoes"], trct["liquido"], places=2
        )
        report = self.env.ref("l10n_br_hr_payroll_report.action_report_termo_rescisao")
        html = self.env["ir.actions.report"]._render_qweb_html(report.id, payslip.ids)[
            0
        ]
        arvore = etree.fromstring(html, etree.HTMLParser())
        texto = " ".join(
            " ".join("".join(tr.itertext()).split())
            for tr in arvore.xpath("//tr[@class='rescisao-outros']")
        )
        self.assertIn("115.1", texto)
        self.assertIn(excesso.name, texto)

    def test_trct_nao_imprime_de_holerite_que_nao_e_rescisao(self):
        """A ação recusa holerite de outra estrutura (13º, mensal, férias):
        sem TRCT nem termo de quitação assinável para quem não foi desligado."""
        emp = self._create_employee("Mensal")
        contract = self._create_contract(emp)
        mensal = self._create_payslip(emp, contract)
        report = self.env.ref("l10n_br_hr_payroll_report.action_report_termo_rescisao")
        with self.assertRaises(UserError):
            self.env["ir.actions.report"]._render_qweb_html(report.id, mensal.ids)

    # ── TG-136: 13º proporcional (63) e 13º do aviso indenizado (70) ────

    def _rescisao_aviso(self, date_start, date_to, wage=2000.00):
        emp = self._create_employee()
        contract = self._create_contract(emp, wage=wage, date_start=date_start)
        payslip = self.env["hr.payslip"].create(
            {
                "name": f"Rescisão - {emp.name}",
                "employee_id": emp.id,
                "contract_id": contract.id,
                "struct_id": self.structure_rescisao.id,
                "date_from": date_to.replace(day=1),
                "date_to": date_to,
                "l10n_br_tipo_rescisao": "sem_justa_causa",
                "l10n_br_aviso_previo": "indenizado",
            }
        )
        payslip.compute_sheet()
        return payslip

    def _detalhe(self, trct, campo):
        return {c: a for c, _r, _v, a in trct["verbas"]}[campo]

    def test_trct_63_e_70_mostram_os_avos_de_cada_rubrica(self):
        """63 só com os avos do proporcional e 70 com os do aviso (30 dias de
        aviso a partir de 30/11: 11 avos + 1)."""
        payslip = self._rescisao_aviso(date(2025, 7, 1), date(2026, 11, 30))
        trct = self._trct(payslip)
        self.assertEqual(self._detalhe(trct, "63"), "11/12 avos")
        self.assertEqual(self._detalhe(trct, "70"), "1/12 avos")
        self.assertAlmostEqual(
            self._valor(trct, "verbas", "63"),
            self._linha(payslip, "DECIMO_RESCISAO"),
            places=2,
        )
        self.assertAlmostEqual(
            self._valor(trct, "verbas", "70"),
            self._linha(payslip, "DECIMO_AVISO_INDENIZADO"),
            places=2,
        )
        self.assertGreater(self._valor(trct, "verbas", "70"), 0)

    def test_trct_aviso_de_90_dias_com_dispensa_em_31_12(self):
        """Aviso de 90 dias: o 63 nunca passa de 12/12 e o 70 leva os 3 avos
        de janeiro a março."""
        payslip = self._rescisao_aviso(date(2006, 1, 1), date(2026, 12, 31))
        trct = self._trct(payslip)
        self.assertEqual(self._detalhe(trct, "63"), "12/12 avos")
        self.assertEqual(self._detalhe(trct, "70"), "3/12 avos")
        self.assertAlmostEqual(self._valor(trct, "verbas", "63"), 2000.00, places=2)
        self.assertAlmostEqual(self._valor(trct, "verbas", "70"), 500.00, places=2)

    def test_trct_70_sem_valor_nao_mostra_avos(self):
        """Sem 13º do aviso (aviso trabalhado) o 70 fica em branco."""
        payslip = self._rescisao_sem_justa_causa()
        payslip.write({"l10n_br_aviso_previo": "trabalhado"})
        payslip.compute_sheet()
        trct = self._trct(payslip)
        self.assertEqual(self._valor(trct, "verbas", "70"), 0.0)
        self.assertFalse(self._detalhe(trct, "70"))

    def test_trct_holerite_calculado_antes_da_rubrica_do_aviso(self):
        """Holerite calculado na 1.10.0 (sem DECIMO_AVISO_INDENIZADO, com o 13º
        inteiro no DECIMO_RESCISAO): o 63 mostra os avos totais e o 70 fica em
        branco."""
        payslip = self._rescisao_aviso(date(2025, 7, 1), date(2026, 11, 30))
        avos_totais = payslip.l10n_br_avos_13
        aviso = payslip.line_ids.filtered(
            lambda ln: ln.code == "DECIMO_AVISO_INDENIZADO"
        )
        decimo = payslip.line_ids.filtered(lambda ln: ln.code == "DECIMO_RESCISAO")
        self.assertTrue(aviso)
        inteiro = decimo.total + aviso.total
        decimo.write({"amount": inteiro})
        aviso.unlink()
        trct = self._trct(payslip)
        self.assertEqual(self._detalhe(trct, "63"), f"{avos_totais}/12 avos")
        self.assertEqual(avos_totais, 12)
        self.assertAlmostEqual(self._valor(trct, "verbas", "63"), inteiro, places=2)
        self.assertEqual(self._valor(trct, "verbas", "70"), 0.0)
        self.assertFalse(self._detalhe(trct, "70"))
