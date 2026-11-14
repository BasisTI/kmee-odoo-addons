# Copyright 2026 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""TG-97: a rescisão desconta o 13º do ano já pago (1ª e 2ª parcelas).

- 1ª parcela (adiantamento) confirmada: o 13º proporcional da rescisão sai
  inteiro e o adiantamento vira desconto próprio (ADIANTAMENTO_13, natureza
  9214 do eSocial), limitado ao líquido.
- 2ª parcela (ou 13º integral) confirmada: o 13º do ano está quitado e a
  rescisão paga só a diferença dos avos; INSS, IRRF e FGTS consideram o
  recolhido.
- Só holerite confirmado, em vigor e do mesmo contrato e ano conta.
"""
from datetime import date

from odoo.exceptions import UserError
from odoo.tests import tagged

from .common import VacationCommon

INICIO_PADRAO = date(2020, 1, 1)


@tagged("post_install", "-at_install")
class TestDecimoPagoRescisao(VacationCommon):
    def _contrato(self, nome, wage=2500.00, inicio=INICIO_PADRAO):
        emp = self._create_employee(nome)
        return emp, self._create_contract(emp, wage=wage, date_start=inicio)

    def _parcela(self, emp, contract, estrutura, confirmar=True, ano=2026, mes=None):
        mes = mes or (11 if estrutura == self.structure_13_primeira else 12)
        slip = self.env["hr.payslip"].create(
            {
                "name": "13º",
                "employee_id": emp.id,
                "contract_id": contract.id,
                "struct_id": estrutura.id,
                "date_from": date(ano, mes, 1),
                "date_to": date(ano, mes, 28),
                "company_id": self.env.company.id,
            }
        )
        slip.compute_sheet()
        if confirmar:
            slip.action_payslip_done()
        return slip

    def _rescisao(self, emp, contract, ate, tipo="pedido_demissao", **extra):
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

    # ── 1ª parcela: desconto próprio ───────────────────────────────────

    def test_primeira_parcela_paga_e_descontada_do_liquido(self):
        """Caso P002/R02: 13º proporcional inteiro e adiantamento de 1.250,00."""
        emp, contract = self._contrato("13 pago 1ª")
        primeira = self._parcela(emp, contract, self.structure_13_primeira)
        self.assertAlmostEqualMoney(self._g(primeira, "ADIANTAMENTO_13"), 1250.00)
        resc = self._rescisao(emp, contract, date(2026, 12, 10))
        self.assertAlmostEqualMoney(self._g(resc, "DECIMO_RESCISAO"), 2291.67)
        self.assertAlmostEqualMoney(self._g(resc, "ADIANTAMENTO_13"), 1250.00)
        sem = self._rescisao(*self._contrato("13 pago 1ª ref"), date(2026, 12, 10))
        self.assertAlmostEqualMoney(self._g(resc, "NET"), self._g(sem, "NET") - 1250.00)
        categoria = resc.line_ids.filtered(lambda ln: ln.code == "ADIANTAMENTO_13")
        self.assertEqual(categoria.category_id.code, "DED")

    def test_primeira_parcela_em_rascunho_nao_e_descontada(self):
        emp, contract = self._contrato("13 pago rascunho")
        self._parcela(emp, contract, self.structure_13_primeira, confirmar=False)
        resc = self._rescisao(emp, contract, date(2026, 12, 10))
        self.assertEqual(self._g(resc, "ADIANTAMENTO_13"), 0.0)

    def test_primeira_parcela_de_outro_ano_nao_e_descontada(self):
        emp, contract = self._contrato("13 pago outro ano")
        self._parcela(emp, contract, self.structure_13_primeira, ano=2025)
        resc = self._rescisao(emp, contract, date(2026, 12, 10))
        self.assertEqual(self._g(resc, "ADIANTAMENTO_13"), 0.0)

    def test_primeira_parcela_de_outro_contrato_nao_e_descontada(self):
        emp, contract = self._contrato("13 pago outro contrato")
        outro_emp, outro = self._contrato("13 pago outra pessoa")
        self._parcela(outro_emp, outro, self.structure_13_primeira)
        resc = self._rescisao(emp, contract, date(2026, 12, 10))
        self.assertEqual(self._g(resc, "ADIANTAMENTO_13"), 0.0)

    def test_estorno_da_primeira_parcela_devolve_ao_calculo(self):
        emp, contract = self._contrato("13 pago estorno")
        primeira = self._parcela(emp, contract, self.structure_13_primeira)
        resc = self._rescisao(emp, contract, date(2026, 12, 10))
        self.assertAlmostEqualMoney(self._g(resc, "ADIANTAMENTO_13"), 1250.00)
        primeira.refund_sheet()
        self.assertEqual(self._g(resc, "ADIANTAMENTO_13"), 0.0)

    def test_confirmar_a_primeira_parcela_recalcula_a_rescisao_aberta(self):
        emp, contract = self._contrato("13 pago recalcula")
        primeira = self._parcela(emp, contract, self.structure_13_primeira, False)
        resc = self._rescisao(emp, contract, date(2026, 12, 10))
        self.assertEqual(self._g(resc, "ADIANTAMENTO_13"), 0.0)
        primeira.action_payslip_done()
        self.assertAlmostEqualMoney(self._g(resc, "ADIANTAMENTO_13"), 1250.00)

    def test_rescisao_confirmada_recusa_mudar_a_parcela(self):
        emp, contract = self._contrato("13 pago confirmada")
        primeira = self._parcela(emp, contract, self.structure_13_primeira)
        resc = self._rescisao(emp, contract, date(2026, 12, 10))
        resc.action_payslip_done()
        with self.assertRaises(UserError):
            primeira.refund_sheet()

    def test_justa_causa_desconta_o_adiantamento_limitado_ao_liquido(self):
        """Sem 13º devido, o adiantamento é compensado no que houver."""
        emp, contract = self._contrato("13 pago justa causa")
        self._parcela(emp, contract, self.structure_13_primeira)
        resc = self._rescisao(emp, contract, date(2026, 12, 10), "justa_causa")
        self.assertEqual(self._g(resc, "DECIMO_RESCISAO"), 0.0)
        disponivel = (
            self._g(resc, "SALDO_SALARIO")
            + self._g(resc, "FERIAS_VENCIDAS")
            + self._g(resc, "ADICIONAL_FERIAS_VENCIDAS")
        )
        disponivel -= self._g(resc, "INSS") + self._g(resc, "IRRF")
        desconto = self._g(resc, "ADIANTAMENTO_13")
        self.assertAlmostEqualMoney(desconto, min(1250.00, disponivel))
        self.assertGreaterEqual(self._g(resc, "NET"), 0.0)
        self.assertAlmostEqualMoney(
            desconto + self._g(resc, "NAO_DESCONTADO_ADIANTAMENTO_13"), 1250.00
        )

    def test_desconto_nunca_deixa_o_liquido_negativo(self):
        """Rescisão em janeiro com a 1ª parcela do mesmo ano: líquido não negativo."""
        emp, contract = self._contrato("13 pago liquido", wage=2500.00)
        self._parcela(emp, contract, self.structure_13_primeira, mes=1)
        resc = self._rescisao(emp, contract, date(2026, 1, 5), "justa_causa")
        self.assertGreaterEqual(self._g(resc, "NET"), 0.0)
        self.assertAlmostEqualMoney(
            self._g(resc, "ADIANTAMENTO_13")
            + self._g(resc, "NAO_DESCONTADO_ADIANTAMENTO_13"),
            1250.00,
        )

    def test_culpa_reciproca_paga_metade_e_desconta_o_adiantamento(self):
        emp, contract = self._contrato("13 pago culpa recíproca")
        self._parcela(emp, contract, self.structure_13_primeira)
        resc = self._rescisao(emp, contract, date(2026, 12, 10), "culpa_reciproca")
        avos = resc.l10n_br_avos_13
        self.assertAlmostEqualMoney(
            self._g(resc, "DECIMO_RESCISAO"), 2500.00 * avos / 12 / 2
        )
        self.assertAlmostEqualMoney(self._g(resc, "ADIANTAMENTO_13"), 1250.00)

    # ── 2ª parcela: quitado, só a diferença dos avos ───────────────────

    def _cenario_dezembro(self, nome, tipo="sem_justa_causa", **extra):
        """2ª parcela de 2026 (bruto 2.000,00) e dispensa em 22/12 com aviso
        indenizado até 24/01/2027 (1 avo de 2027)."""
        emp, contract = self._contrato(nome, 2000.00, date(2025, 6, 1))
        segunda = self._parcela(emp, contract, self.structure_13_segunda)
        valores = {"l10n_br_aviso_previo": "indenizado"}
        valores.update(extra)
        resc = self._rescisao(emp, contract, date(2026, 12, 22), tipo, **valores)
        return emp, contract, segunda, resc

    def test_segunda_parcela_paga_so_a_diferenca_dos_avos(self):
        _emp, _ct, segunda, resc = self._cenario_dezembro("13 quitado")
        self.assertAlmostEqualMoney(self._g(segunda, "DECIMO_TERCEIRO_BRUTO"), 2000.00)
        self.assertEqual(resc.l10n_br_avos_13, 13)
        self.assertAlmostEqualMoney(self._g(resc, "DECIMO_RESCISAO"), 166.67)
        self.assertEqual(self._g(resc, "ADIANTAMENTO_13"), 0.0)

    def test_segunda_parcela_encargos_consideram_o_retido(self):
        """INSS, IRRF e FGTS do ano: o da 2ª parcela mais o da rescisão igualam
        os de uma rescisão sem 13º pago."""
        _emp, _ct, segunda, resc = self._cenario_dezembro("13 quitado encargos")
        ref = self._rescisao(
            *self._contrato("13 quitado encargos ref", 2000.00, date(2025, 6, 1)),
            date(2026, 12, 22),
            "sem_justa_causa",
            l10n_br_aviso_previo="indenizado",
        )
        self.assertAlmostEqualMoney(self._g(ref, "DECIMO_RESCISAO"), 2166.67)
        for codigo, rescisao in (("INSS_13", "INSS_13"), ("IRRF_13", "IRRF_13")):
            self.assertAlmostEqualMoney(
                self._g(segunda, codigo) + self._g(resc, rescisao),
                self._g(ref, rescisao),
                msg=codigo,
            )
        self.assertAlmostEqualMoney(
            self._g(segunda, "FGTS") + self._g(resc, "FGTS_13"),
            self._g(ref, "FGTS_13"),
        )

    def test_segunda_parcela_paga_em_dezembro_nao_duplica_com_aviso_trabalhado(self):
        """Pedido de demissão em dezembro com a 2ª parcela paga: 13º zero."""
        emp, contract = self._contrato("13 quitado trabalhado", 2000.00)
        self._parcela(emp, contract, self.structure_13_segunda)
        resc = self._rescisao(emp, contract, date(2026, 12, 22))
        self.assertEqual(self._g(resc, "DECIMO_RESCISAO"), 0.0)
        self.assertEqual(self._g(resc, "INSS_13"), 0.0)
        self.assertEqual(self._g(resc, "IRRF_13"), 0.0)
        self.assertEqual(self._g(resc, "FGTS_13"), 0.0)

    def test_segunda_parcela_paga_a_mais_nao_gera_valor_negativo(self):
        """Justa causa depois da 2ª parcela: o 13º quitado não é cobrado de volta."""
        emp, contract = self._contrato("13 quitado a mais", 2000.00)
        self._parcela(emp, contract, self.structure_13_segunda)
        resc = self._rescisao(emp, contract, date(2026, 12, 22), "justa_causa")
        self.assertEqual(self._g(resc, "DECIMO_RESCISAO"), 0.0)
        self.assertEqual(self._g(resc, "ADIANTAMENTO_13"), 0.0)
        self.assertGreaterEqual(self._g(resc, "NET"), 0.0)

    def test_segunda_parcela_estornada_devolve_ao_calculo(self):
        _emp, _ct, segunda, resc = self._cenario_dezembro("13 quitado estorno")
        self.assertAlmostEqualMoney(self._g(resc, "DECIMO_RESCISAO"), 166.67)
        segunda.refund_sheet()
        self.assertAlmostEqualMoney(self._g(resc, "DECIMO_RESCISAO"), 2166.67)

    def test_segunda_parcela_confirmada_recalcula_a_rescisao_aberta(self):
        emp, contract = self._contrato("13 quitado confirma", 2000.00, date(2025, 6, 1))
        segunda = self._parcela(emp, contract, self.structure_13_segunda, False)
        resc = self._rescisao(
            emp,
            contract,
            date(2026, 12, 22),
            "sem_justa_causa",
            l10n_br_aviso_previo="indenizado",
        )
        self.assertAlmostEqualMoney(self._g(resc, "DECIMO_RESCISAO"), 2166.67)
        segunda.action_payslip_done()
        self.assertAlmostEqualMoney(self._g(resc, "DECIMO_RESCISAO"), 166.67)

    def test_primeira_e_segunda_parcela_nao_contam_em_dobro(self):
        """A 2ª parcela já abate a 1ª: o adiantamento não é descontado de novo."""
        emp, contract = self._contrato("13 pago as duas", 2000.00, date(2025, 6, 1))
        self._parcela(emp, contract, self.structure_13_primeira)
        segunda = self.env["hr.payslip"].create(
            {
                "name": "13º 2ª",
                "employee_id": emp.id,
                "contract_id": contract.id,
                "struct_id": self.structure_13_segunda.id,
                "date_from": date(2026, 12, 1),
                "date_to": date(2026, 12, 20),
                "l10n_br_primeira_parcela_13_paga": 1000.00,
                "company_id": self.env.company.id,
            }
        )
        segunda.compute_sheet()
        segunda.action_payslip_done()
        resc = self._rescisao(emp, contract, date(2026, 12, 22))
        self.assertEqual(self._g(resc, "ADIANTAMENTO_13"), 0.0)
        self.assertEqual(self._g(resc, "DECIMO_RESCISAO"), 0.0)
