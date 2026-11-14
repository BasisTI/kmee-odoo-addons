# Copyright 2026 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""TG-141: a rescisão desconta o 13º pago além do devido pela 2ª parcela.

Quando a 2ª parcela (ou o 13º integral) confirmada já quitou mais 13º do que a
rescisão reconhece como devido (justa causa, culpa recíproca, pedido de
demissão antes de 15/12 com a 2ª parcela pagando 12 avos):

- o excesso sai como desconto próprio (``DESCONTO_13_EXCESSO``), limitado ao
  líquido e ao teto de um mês de remuneração (CLT art. 477, §5º), somado aos
  demais descontos; o que não couber vai à linha informativa;
- INSS, IRRF e pensão do 13º são calculados sobre o devido e o retido a mais
  volta em ``DEVOLUCAO_ENCARGOS_13``;
- o FGTS do 13º não é recolhido de novo.
"""
from datetime import date

from odoo.exceptions import UserError
from odoo.tests import tagged

from .common import VacationCommon

INICIO_PADRAO = date(2020, 1, 1)


@tagged("post_install", "-at_install")
class TestDecimoExcessoRescisao(VacationCommon):
    def _contrato(self, nome, wage=3000.00, inicio=INICIO_PADRAO):
        emp = self._create_employee(nome)
        return emp, self._create_contract(emp, wage=wage, date_start=inicio)

    def _segunda_parcela(self, emp, contract, confirmar=True, primeira=0.0):
        slip = self.env["hr.payslip"].create(
            {
                "name": "13º 2ª",
                "employee_id": emp.id,
                "contract_id": contract.id,
                "struct_id": self.structure_13_segunda.id,
                "date_from": date(2026, 12, 1),
                "date_to": date(2026, 12, 20),
                "l10n_br_primeira_parcela_13_paga": primeira,
                "company_id": self.env.company.id,
            }
        )
        slip.compute_sheet()
        if confirmar:
            slip.action_payslip_done()
        return slip

    def _rescisao(self, emp, contract, ate, tipo, **extra):
        valores = {
            "name": "Rescisão",
            "employee_id": emp.id,
            "contract_id": contract.id,
            "struct_id": self.structure_rescisao.id,
            "date_from": ate.replace(day=1),
            "date_to": ate,
            "l10n_br_tipo_rescisao": tipo,
            "l10n_br_aviso_previo": "nao_aplicavel",
            "company_id": self.env.company.id,
        }
        valores.update(extra)
        resc = self.env["hr.payslip"].create(valores)
        resc.compute_sheet()
        return resc

    def _g(self, slip, code):
        return self._get_line_total(slip, code)

    def _liquido_disponivel(self, resc):
        """Créditos da rescisão menos os encargos, antes dos descontos próprios."""
        creditos = sum(
            self._g(resc, c)
            for c in (
                "SALDO_SALARIO",
                "DECIMO_RESCISAO",
                "FERIAS_INDENIZADAS",
                "ADICIONAL_FERIAS_INDENIZADAS",
                "FERIAS_VENCIDAS",
                "ADICIONAL_FERIAS_VENCIDAS",
                "AVISO_PREVIO_INDENIZADO",
                "INDENIZACAO_ART_479",
                "DEVOLUCAO_ENCARGOS_13",
            )
        )
        encargos = sum(
            self._g(resc, c)
            for c in (
                "INSS",
                "INSS_13",
                "IRRF",
                "IRRF_13",
                "PENSAO_ALIMENTICIA",
                "PENSAO_ALIMENTICIA_13",
            )
        )
        return creditos - encargos

    # ── Caso 1: justa causa com 1ª e 2ª parcelas pagas ─────────────────

    def test_justa_causa_com_as_duas_parcelas_desconta_o_13_inteiro(self):
        emp, contract = self._contrato("excesso justa causa")
        segunda = self._segunda_parcela(emp, contract, primeira=1500.00)
        self.assertAlmostEqualMoney(self._g(segunda, "DECIMO_TERCEIRO_BRUTO"), 3000.00)
        resc = self._rescisao(emp, contract, date(2026, 12, 22), "justa_causa")
        self.assertEqual(self._g(resc, "DECIMO_RESCISAO"), 0.0)
        self.assertEqual(self._g(resc, "DECIMO_DEVIDO"), 0.0)
        # Os encargos do 13º voltam inteiros: o devido é zero.
        self.assertEqual(self._g(resc, "INSS_13"), 0.0)
        self.assertEqual(self._g(resc, "IRRF_13"), 0.0)
        self.assertAlmostEqualMoney(
            self._g(resc, "DEVOLUCAO_ENCARGOS_13"),
            self._g(segunda, "INSS_13") + self._g(segunda, "IRRF_13"),
        )
        # O líquido limita o desconto: só o que há de crédito na rescisão.
        desconto = self._g(resc, "DESCONTO_13_EXCESSO")
        self.assertAlmostEqualMoney(desconto, self._liquido_disponivel(resc))
        self.assertGreater(desconto, 0.0)
        self.assertAlmostEqualMoney(
            desconto + self._g(resc, "NAO_DESCONTADO_13_EXCESSO"), 3000.00
        )
        self.assertAlmostEqualMoney(self._g(resc, "NET"), 0.0)
        linha = resc.line_ids.filtered(lambda ln: ln.code == "DESCONTO_13_EXCESSO")
        self.assertEqual(linha.category_id.code, "DED")
        info = resc.line_ids.filtered(lambda ln: ln.code == "NAO_DESCONTADO_13_EXCESSO")
        self.assertEqual(info.category_id.code, "INFO")

    # ── Caso 2: culpa recíproca, 13º pela metade, salário 4.000,00 ─────

    def test_culpa_reciproca_recalcula_os_encargos_sobre_o_devido(self):
        emp, contract = self._contrato("excesso culpa recíproca", 4000.00)
        segunda = self._segunda_parcela(emp, contract)
        self.assertAlmostEqualMoney(self._g(segunda, "INSS_13"), 368.60)
        resc = self._rescisao(
            emp,
            contract,
            date(2026, 12, 22),
            "culpa_reciproca",
            l10n_br_aviso_previo="indenizado",
        )
        ref = self._rescisao(
            *self._contrato("excesso culpa recíproca ref", 4000.00),
            date(2026, 12, 22),
            "culpa_reciproca",
            l10n_br_aviso_previo="indenizado",
        )
        self.assertAlmostEqualMoney(self._g(resc, "DECIMO_DEVIDO"), 2166.67)
        self.assertAlmostEqualMoney(self._g(ref, "INSS_13"), 170.69)
        self.assertEqual(self._g(resc, "DECIMO_RESCISAO"), 0.0)
        self.assertAlmostEqualMoney(self._g(resc, "DESCONTO_13_EXCESSO"), 1833.33)
        self.assertEqual(self._g(resc, "NAO_DESCONTADO_13_EXCESSO"), 0.0)
        # Retido na 2ª parcela (sobre 4.000,00) menos o devido (sobre 2.166,67):
        # volta ao empregado.
        retido = self._g(segunda, "INSS_13") + self._g(segunda, "IRRF_13")
        devido = self._g(ref, "INSS_13") + self._g(ref, "IRRF_13")
        self.assertAlmostEqualMoney(
            self._g(resc, "DEVOLUCAO_ENCARGOS_13"), retido - devido
        )
        self.assertGreaterEqual(self._g(resc, "DEVOLUCAO_ENCARGOS_13"), 197.91)
        # Encargos do ano: o retido mais o desta rescisão, menos o que volta,
        # igualam os de uma rescisão sem 13º pago.
        self.assertEqual(self._g(resc, "INSS_13"), 0.0)

    def test_culpa_reciproca_liquido_so_perde_o_excesso_menos_a_devolucao(self):
        emp, contract = self._contrato("excesso liquido", 4000.00)
        self._segunda_parcela(emp, contract)
        kw = {"l10n_br_aviso_previo": "indenizado"}
        resc = self._rescisao(
            emp, contract, date(2026, 12, 22), "culpa_reciproca", **kw
        )
        ref = self._rescisao(
            *self._contrato("excesso liquido ref", 4000.00),
            date(2026, 12, 22),
            "culpa_reciproca",
            **kw,
        )
        # Sem 13º pago a rescisão pagaria o devido (2.166,67) menos os encargos;
        # com ele, o empregado devolve o excesso e recebe os encargos de volta.
        self.assertAlmostEqualMoney(
            self._g(resc, "NET"),
            self._g(ref, "NET")
            - self._g(ref, "DECIMO_RESCISAO")
            + self._g(ref, "INSS_13")
            + self._g(ref, "IRRF_13")
            + self._g(resc, "DEVOLUCAO_ENCARGOS_13")
            - self._g(resc, "DESCONTO_13_EXCESSO"),
        )

    # ── Caso 3: pedido de demissão antes de 15/12, 2ª parcela com 12 avos ─

    def test_pedido_de_demissao_antes_de_15_12_desconta_o_avo_a_mais(self):
        emp, contract = self._contrato("excesso pedido demissão")
        self._segunda_parcela(emp, contract)
        resc = self._rescisao(emp, contract, date(2026, 12, 10), "pedido_demissao")
        self.assertEqual(resc.l10n_br_avos_13, 11)
        self.assertAlmostEqualMoney(self._g(resc, "DECIMO_DEVIDO"), 2750.00)
        self.assertEqual(self._g(resc, "DECIMO_RESCISAO"), 0.0)
        self.assertAlmostEqualMoney(self._g(resc, "DESCONTO_13_EXCESSO"), 250.00)
        self.assertEqual(self._g(resc, "NAO_DESCONTADO_13_EXCESSO"), 0.0)
        self.assertGreater(self._g(resc, "DEVOLUCAO_ENCARGOS_13"), 0.0)

    # ── Teto do art. 477 §5º e ordem dos descontos ─────────────────────

    def test_aviso_nao_cumprido_vem_antes_do_excesso_e_o_conjunto_respeita_o_teto(
        self,
    ):
        emp, contract = self._contrato("excesso teto")
        self._segunda_parcela(emp, contract)
        resc = self._rescisao(
            emp,
            contract,
            date(2026, 12, 10),
            "pedido_demissao",
            l10n_br_aviso_previo="nao_cumprido",
        )
        aviso = self._g(resc, "DESCONTO_AVISO_PREVIO")
        excesso = self._g(resc, "DESCONTO_13_EXCESSO")
        self.assertGreater(aviso, 0.0)
        self.assertLessEqual(aviso + excesso, 3000.00 + 0.005)
        self.assertGreaterEqual(self._g(resc, "NET"), 0.0)
        self.assertAlmostEqualMoney(
            excesso + self._g(resc, "NAO_DESCONTADO_13_EXCESSO"), 250.00
        )
        self.assertLessEqual(excesso, self._liquido_disponivel(resc) - aviso + 0.005)

    def test_sem_excesso_nao_ha_desconto_nem_devolucao(self):
        """2ª parcela abaixo do devido: só a diferença dos avos, sem desconto."""
        emp, contract = self._contrato("sem excesso", 2000.00, date(2025, 6, 1))
        segunda = self._segunda_parcela(emp, contract)
        resc = self._rescisao(
            emp,
            contract,
            date(2026, 12, 22),
            "sem_justa_causa",
            l10n_br_aviso_previo="indenizado",
        )
        self.assertAlmostEqualMoney(self._g(resc, "DECIMO_RESCISAO"), 166.67)
        for codigo in (
            "DESCONTO_13_EXCESSO",
            "NAO_DESCONTADO_13_EXCESSO",
            "DEVOLUCAO_ENCARGOS_13",
        ):
            self.assertEqual(self._g(resc, codigo), 0.0, codigo)
        self.assertAlmostEqualMoney(
            self._g(segunda, "INSS_13") + self._g(resc, "INSS_13"),
            self._g(
                self._rescisao(
                    *self._contrato("sem excesso ref", 2000.00, date(2025, 6, 1)),
                    date(2026, 12, 22),
                    "sem_justa_causa",
                    l10n_br_aviso_previo="indenizado",
                ),
                "INSS_13",
            ),
        )

    # ── FGTS do 13º ─────────────────────────────────────────────────────

    def test_fgts_do_13_nao_recolhe_de_novo_e_a_multa_conta_o_ja_recolhido(self):
        emp, contract = self._contrato("excesso fgts")
        segunda = self._segunda_parcela(emp, contract)
        resc = self._rescisao(emp, contract, date(2026, 12, 10), "pedido_demissao")
        self.assertGreater(self._g(segunda, "FGTS"), 0.0)
        self.assertEqual(self._g(resc, "FGTS_13"), 0.0)
        self.assertAlmostEqualMoney(
            resc._l10n_br_fgts_13_primeira_depositado(contract),
            self._g(segunda, "FGTS"),
        )

    # ── Integridade entre holerites ─────────────────────────────────────

    def test_confirmar_a_segunda_parcela_recalcula_a_rescisao_aberta(self):
        emp, contract = self._contrato("excesso recalcula")
        segunda = self._segunda_parcela(emp, contract, confirmar=False)
        resc = self._rescisao(emp, contract, date(2026, 12, 10), "pedido_demissao")
        self.assertEqual(self._g(resc, "DESCONTO_13_EXCESSO"), 0.0)
        self.assertAlmostEqualMoney(self._g(resc, "DECIMO_RESCISAO"), 2750.00)
        segunda.action_payslip_done()
        self.assertAlmostEqualMoney(self._g(resc, "DESCONTO_13_EXCESSO"), 250.00)
        self.assertEqual(self._g(resc, "DECIMO_RESCISAO"), 0.0)

    def test_estorno_da_segunda_parcela_tira_o_desconto_da_rescisao_aberta(self):
        emp, contract = self._contrato("excesso estorno")
        segunda = self._segunda_parcela(emp, contract)
        resc = self._rescisao(emp, contract, date(2026, 12, 10), "pedido_demissao")
        self.assertAlmostEqualMoney(self._g(resc, "DESCONTO_13_EXCESSO"), 250.00)
        segunda.refund_sheet()
        self.assertEqual(self._g(resc, "DESCONTO_13_EXCESSO"), 0.0)
        self.assertEqual(self._g(resc, "DEVOLUCAO_ENCARGOS_13"), 0.0)
        self.assertAlmostEqualMoney(self._g(resc, "DECIMO_RESCISAO"), 2750.00)

    def test_rescisao_confirmada_recusa_mudar_a_segunda_parcela(self):
        emp, contract = self._contrato("excesso confirmada")
        segunda = self._segunda_parcela(emp, contract)
        resc = self._rescisao(emp, contract, date(2026, 12, 10), "pedido_demissao")
        resc.action_payslip_done()
        with self.assertRaises(UserError):
            segunda.refund_sheet()
