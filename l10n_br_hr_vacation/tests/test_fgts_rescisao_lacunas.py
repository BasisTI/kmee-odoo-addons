# Copyright 2026 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""TG-138: lacunas da base e da integridade do FGTS na rescisão.

Saldo informado = extrato do FGTS Digital posicionado ANTES do mês da rescisão
(R): o extrato só traz depósitos vencidos até R-1 (vencimento no dia 20 do mês
seguinte à competência), então a base da multa soma as competências R-1 e R
(Lei 8.036/90 art. 18 §1º; Decreto 99.684/90 art. 9º §1º).
"""
from datetime import date

from odoo.exceptions import UserError
from odoo.tests import tagged

from odoo.addons.l10n_br_hr_payroll.models.salary_rules_br import round_money

from .common import VacationCommon


@tagged("post_install", "-at_install")
class TestFgtsRescisaoLacunas(VacationCommon):
    def _contrato(self, nome="FGTS lacunas", wage=2500.00):
        emp = self._create_employee(nome)
        contract = self._create_contract(emp, wage=wage, date_start=date(2020, 1, 1))
        return emp, contract

    def _holerite(self, emp, contract, struct, de, ate, calcular=True, **extra):
        valores = {
            "name": "Holerite %s" % de,
            "employee_id": emp.id,
            "contract_id": contract.id,
            "struct_id": struct.id,
            "date_from": de,
            "date_to": ate,
            "company_id": self.env.company.id,
        }
        valores.update(extra)
        slip = self.env["hr.payslip"].create(valores)
        if calcular:
            slip.compute_sheet()
        return slip

    def _mensal(self, emp, contract, mes, ano=2026, confirmar=False):
        ultimo = 28 if mes == 2 else 30
        slip = self._holerite(
            emp,
            contract,
            self.structure_clt,
            date(ano, mes, 1),
            date(ano, mes, ultimo),
        )
        if confirmar:
            slip.action_payslip_done()
        return slip

    def _rescisao(self, emp, contract, ate, calcular=True, **extra):
        valores = {
            "l10n_br_tipo_rescisao": "sem_justa_causa",
            "l10n_br_aviso_previo": "trabalhado",
            "l10n_br_fgts_saldo_conta": 10000.00,
        }
        valores.update(extra)
        return self._holerite(
            emp,
            contract,
            self.structure_rescisao,
            ate.replace(day=1),
            ate,
            calcular,
            **valores,
        )

    def _multa(self, resc):
        return self._get_line_total(resc, "MULTA_FGTS")

    def _esperada(self, resc, *extras, saldo=10000.00):
        """(saldo + depósitos da rescisão + extras) x 40%."""
        depositos = sum(
            self._get_line_total(resc, codigo)
            for codigo in ("FGTS", "FGTS_13", "FGTS_AVISO")
        )
        return round_money((saldo + depositos + sum(extras)) * 0.40)

    def _parcela(self, emp, contract, mes, confirmar=True):
        slip = self._holerite(
            emp,
            contract,
            self.structure_13_primeira,
            date(2026, mes, 1),
            date(2026, mes, 28),
        )
        if confirmar:
            slip.action_payslip_done()
        return slip

    # --- suspeitas da base da multa -------------------------------------

    def test_deposito_do_mes_anterior_entra_na_base_com_saldo_informado(self):
        emp, contract = self._contrato()
        anterior = self._mensal(emp, contract, 11)
        fgts_ant = self._get_line_total(anterior, "FGTS")
        self.assertGreater(fgts_ant, 0)
        resc = self._rescisao(emp, contract, date(2026, 12, 10))
        self.assertAlmostEqualMoney(self._multa(resc), self._esperada(resc, fgts_ant))

    def test_deposito_de_dois_meses_antes_ja_esta_no_extrato(self):
        emp, contract = self._contrato()
        self._mensal(emp, contract, 10)
        resc = self._rescisao(emp, contract, date(2026, 12, 10))
        self.assertAlmostEqualMoney(self._multa(resc), self._esperada(resc))

    def test_sem_saldo_informado_o_mes_anterior_nao_soma(self):
        """A estimativa 8% x salário x meses já cobre os meses completos."""
        emp, contract = self._contrato()
        self._mensal(emp, contract, 11)
        resc = self._rescisao(
            emp, contract, date(2026, 12, 10), l10n_br_fgts_saldo_conta=0
        )
        outro, contrato_outro = self._contrato("FGTS lacunas sem mensal")
        sem = self._rescisao(
            outro, contrato_outro, date(2026, 12, 10), l10n_br_fgts_saldo_conta=0
        )
        self.assertAlmostEqualMoney(self._multa(resc), self._multa(sem))

    def test_recibo_de_ferias_do_mes_entra_na_base(self):
        emp, contract = self._contrato()
        alloc = self.env["hr.leave.allocation"].create(
            {
                "employee_id": emp.id,
                "holiday_status_id": self.leave_type_ferias.id,
                "date_from": date(2025, 1, 2),
                "date_to": date(2026, 1, 1),
            }
        )
        alloc.action_validate()
        recibo = self._holerite(
            emp,
            contract,
            self.structure_ferias,
            date(2026, 12, 1),
            date(2026, 12, 10),
            l10n_br_ferias_allocation_id=alloc.id,
            l10n_br_dias_periodo_gozado=10,
        )
        fgts = self._get_line_total(recibo, "FGTS")
        self.assertGreater(fgts, 0)
        resc = self._rescisao(emp, contract, date(2026, 12, 20))
        self.assertAlmostEqualMoney(self._multa(resc), self._esperada(resc, fgts))

    def test_13o_ja_no_extrato_nao_soma_de_novo(self):
        """1ª parcela paga em janeiro: vencida em fevereiro, já está no saldo."""
        emp, contract = self._contrato()
        self._parcela(emp, contract, 1)
        resc = self._rescisao(emp, contract, date(2026, 12, 10))
        self.assertAlmostEqualMoney(self._multa(resc), self._esperada(resc))

    def test_13o_do_mes_anterior_soma_com_saldo_informado(self):
        emp, contract = self._contrato()
        parcela = self._parcela(emp, contract, 11)
        resc = self._rescisao(emp, contract, date(2026, 12, 10))
        depositos = (
            self._get_line_total(resc, "FGTS")
            + self._get_line_total(resc, "FGTS_13")
            + self._get_line_total(resc, "FGTS_AVISO")
            + self._get_line_total(parcela, "FGTS")
        )
        self.assertAlmostEqualMoney(
            self._multa(resc), round_money((10000.00 + depositos) * 0.40)
        )

    # --- integridade -----------------------------------------------------

    def test_compute_sheet_de_holerite_confirmado_e_recusado(self):
        emp, contract = self._contrato()
        resc = self._rescisao(emp, contract, date(2026, 12, 10))
        resc.action_payslip_done()
        with self.assertRaises(UserError):
            resc.compute_sheet()
        self.assertEqual(resc.state, "done")

    def test_write_direto_na_linha_do_mensal_com_rescisao_confirmada(self):
        emp, contract = self._contrato()
        mensal = self._mensal(emp, contract, 12)
        resc = self._rescisao(emp, contract, date(2026, 12, 20))
        resc.action_payslip_done()
        linha = mensal.line_ids.filtered(lambda ln: ln.code == "FGTS")
        with self.assertRaises(UserError):
            linha.write({"amount": linha.amount + 50.0})

    def test_write_direto_na_linha_do_mensal_recalcula_rescisao_aberta(self):
        emp, contract = self._contrato()
        mensal = self._mensal(emp, contract, 12)
        resc = self._rescisao(emp, contract, date(2026, 12, 20))
        antes = self._multa(resc)
        linha = mensal.line_ids.filtered(lambda ln: ln.code == "FGTS")
        linha.write({"amount": linha.amount + 50.0})
        self.assertAlmostEqualMoney(self._multa(resc) - antes, 20.0)

    def test_state_done_em_lote_recalcula_a_rescisao_antes_de_confirmar(self):
        emp, contract = self._contrato()
        parcela = self._parcela(emp, contract, 11, confirmar=False)
        resc = self._rescisao(emp, contract, date(2026, 12, 10))
        self.assertAlmostEqualMoney(self._get_line_total(resc, "FGTS_13"), 183.33)
        (parcela | resc).write({"state": "done"})
        self.assertEqual(resc.state, "done")
        self.assertAlmostEqualMoney(self._get_line_total(resc, "FGTS_13"), 83.33)

    def test_recusa_cita_o_fgts(self):
        emp, contract = self._contrato()
        parcela = self._parcela(emp, contract, 11, confirmar=False)
        resc = self._rescisao(emp, contract, date(2026, 12, 10))
        resc.action_payslip_done()
        with self.assertRaises(UserError) as erro:
            parcela.action_payslip_done()
        self.assertIn("FGTS", str(erro.exception))

    # --- regras personalizadas e menores da TG-93 -------------------------

    def _regra(self, codigo):
        return self.structure_rescisao.rule_ids.filtered(lambda r: r.code == codigo)

    def test_net_personalizado_com_multa_avisa_o_gestor(self):
        emp, contract = self._contrato()
        net = self._regra("NET")
        net.amount_python_compute += "\nresult = result + MULTA_FGTS\n"
        resc = self._rescisao(emp, contract, date(2026, 12, 10))
        self.assertIn("NET", resc.l10n_br_aviso_regras)
        self.assertIn("multa do FGTS", resc.l10n_br_aviso_regras)
        notas = " ".join(resc.message_ids.mapped("body"))
        self.assertIn("Retire MULTA_FGTS", notas)
        # Recalcular não repete a nota.
        resc.compute_sheet()
        self.assertEqual(
            sum("Retire MULTA_FGTS" in (m.body or "") for m in resc.message_ids), 1
        )

    def test_net_padrao_nao_avisa(self):
        emp, contract = self._contrato()
        resc = self._rescisao(emp, contract, date(2026, 12, 10))
        self.assertFalse(resc.l10n_br_aviso_regras)
        self.assertFalse(
            resc.message_ids.filtered("body").filtered(
                lambda m: "Retire MULTA_FGTS" in (m.body or "")
            )
        )

    def test_multa_personalizada_sem_o_13o_avisa(self):
        emp, contract = self._contrato()
        multa = self._regra("MULTA_FGTS")
        multa.amount_python_compute = "result = 0.0\n"
        resc = self._rescisao(emp, contract, date(2026, 12, 10))
        self.assertIn("MULTA_FGTS", resc.l10n_br_aviso_regras)

    def test_aprendiz_recolhe_2_por_cento_no_13o(self):
        emp, contract = self._contrato("FGTS aprendiz 13º")
        emp.l10n_br_tipo_contrato = "aprendiz"
        parcela = self._parcela(emp, contract, 11, confirmar=False)
        adiantamento = self._get_line_total(parcela, "ADIANTAMENTO_13")
        self.assertGreater(adiantamento, 0)
        self.assertAlmostEqualMoney(
            self._get_line_total(parcela, "FGTS"), round_money(adiantamento * 0.02)
        )
        resc = self._rescisao(emp, contract, date(2026, 12, 10))
        devido = self._get_line_total(resc, "DECIMO_DEVIDO")
        self.assertAlmostEqualMoney(
            self._get_line_total(resc, "FGTS_13"), round_money(devido * 0.02)
        )

    def test_13_salario_generico_desconta_o_adiantamento_do_liquido(self):
        emp, contract = self._contrato("FGTS 13_SALARIO")
        sem = self._holerite(
            emp, contract, self.structure_13, date(2026, 12, 1), date(2026, 12, 20)
        )
        com = self._holerite(
            emp,
            contract,
            self.structure_13,
            date(2026, 12, 1),
            date(2026, 12, 20),
            l10n_br_primeira_parcela_13_paga=500.00,
        )
        self.assertAlmostEqualMoney(
            self._get_line_total(com, "ADIANTAMENTO_13"), 500.00
        )
        self.assertAlmostEqualMoney(
            self._get_line_total(com, "NET"), self._get_line_total(sem, "NET") - 500.00
        )
