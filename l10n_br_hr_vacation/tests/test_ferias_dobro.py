# Copyright 2026 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""TG-139: férias concedidas depois do período concessivo, pagas em dobro.

CLT art. 137: concedidas fora do concessivo (art. 134), as férias são pagas em
dobro, com o terço. Súmula 81 do TST: se o gozo atravessa o fim do concessivo,
dobram só os dias depois dele. Aquisitivo 2025-01-02 a 2026-01-01; concessivo
até 2027-01-01.
"""
from datetime import date, timedelta

from odoo.exceptions import UserError
from odoo.tests import tagged

from .common import VacationCommon

AQ_INI, AQ_FIM = date(2025, 1, 2), date(2026, 1, 1)


@tagged("post_install", "-at_install")
class TestFeriasDobro(VacationCommon):
    def _caso(self, *_args, wage=3600.0):
        emp = self._create_employee()
        contract = self._create_contract(emp, wage=wage, date_start=date(2024, 1, 2))
        alloc = self.env["hr.leave.allocation"].create(
            {
                "employee_id": emp.id,
                "holiday_status_id": self.leave_type_ferias.id,
                "date_from": AQ_INI,
                "date_to": AQ_FIM,
            }
        )
        alloc.action_validate()
        return emp, contract, alloc

    def _recibo(self, emp, contract, alloc, inicio, dias, abono=0, calcular=True):
        slip = self.env["hr.payslip"].create(
            {
                "name": "Férias",
                "employee_id": emp.id,
                "contract_id": contract.id,
                "struct_id": self.structure_ferias.id,
                "date_from": inicio,
                "date_to": inicio + timedelta(days=dias - 1),
                "l10n_br_ferias_allocation_id": alloc.id,
                "l10n_br_dias_periodo_gozado": dias,
                "l10n_br_dias_abono": abono,
                "company_id": self.env.company.id,
            }
        )
        if calcular:
            slip.compute_sheet()
        return slip

    def test_dentro_do_concessivo_nao_dobra(self):
        emp, contract, alloc = self._caso(None, None)
        slip = self._recibo(emp, contract, alloc, date(2026, 11, 16), 10)
        self.assertEqual(slip.l10n_br_dias_ferias_dobro, 0)
        self.assertAlmostEqualMoney(self._get_line_total(slip, "FERIAS"), 1200)
        self.assertEqual(self._get_line_total(slip, "FERIAS_DOBRO"), 0)
        self.assertEqual(self._get_line_total(slip, "ADICIONAL_FERIAS_DOBRO"), 0)

    def test_ultimo_dia_do_concessivo_nao_dobra(self):
        emp, contract, alloc = self._caso(None, None)
        slip = self._recibo(emp, contract, alloc, date(2026, 12, 23), 10)
        # gozo 23/12 a 01/01: o último dia ainda é do concessivo
        self.assertEqual(slip.date_to, date(2027, 1, 1))
        self.assertEqual(slip.l10n_br_dias_ferias_dobro, 0)
        self.assertEqual(self._get_line_total(slip, "FERIAS_DOBRO"), 0)

    def test_depois_do_concessivo_paga_remuneracao_e_terco_em_dobro(self):
        emp, contract, alloc = self._caso(None, None)
        slip = self._recibo(emp, contract, alloc, date(2027, 2, 1), 10)
        self.assertEqual(slip.l10n_br_dias_ferias_dobro, 10)
        self.assertAlmostEqualMoney(self._get_line_total(slip, "FERIAS"), 1200)
        self.assertAlmostEqualMoney(self._get_line_total(slip, "ADICIONAL_FERIAS"), 400)
        self.assertAlmostEqualMoney(self._get_line_total(slip, "FERIAS_DOBRO"), 1200)
        self.assertAlmostEqualMoney(
            self._get_line_total(slip, "ADICIONAL_FERIAS_DOBRO"), 400
        )

    def test_gozo_que_cruza_o_fim_do_concessivo_dobra_so_os_dias_depois(self):
        """Súmula 81 do TST: 27/12 a 05/01 são 10 dias, 4 depois do concessivo."""
        emp, contract, alloc = self._caso(None, None)
        slip = self._recibo(emp, contract, alloc, date(2026, 12, 27), 10)
        self.assertEqual(slip.l10n_br_dias_ferias_dobro, 4)
        self.assertAlmostEqualMoney(self._get_line_total(slip, "FERIAS"), 1200)
        self.assertAlmostEqualMoney(self._get_line_total(slip, "FERIAS_DOBRO"), 480)
        self.assertAlmostEqualMoney(
            self._get_line_total(slip, "ADICIONAL_FERIAS_DOBRO"), 160
        )

    def test_dobra_nao_incide_inss_nem_fgts_e_incide_irrf(self):
        emp, contract, alloc = self._caso()
        simples = self._recibo(emp, contract, alloc, date(2026, 11, 16), 10)
        emp, contract, alloc = self._caso()
        dobro = self._recibo(emp, contract, alloc, date(2027, 2, 1), 10)
        for codigo in ("GROSS", "INSS", "FGTS"):
            self.assertAlmostEqualMoney(
                self._get_line_total(dobro, codigo),
                self._get_line_total(simples, codigo),
                codigo,
            )
        self.assertAlmostEqualMoney(
            self._get_line_total(dobro, "BASE_IRRF"),
            self._get_line_total(simples, "BASE_IRRF") + 1600,
        )
        self.assertAlmostEqualMoney(
            self._get_line_total(dobro, "NET"),
            self._get_line_total(simples, "NET")
            + 1600
            - (
                self._get_line_total(dobro, "IRRF")
                - self._get_line_total(simples, "IRRF")
            ),
        )

    def test_abono_nao_dobra(self):
        """Vende 10 dias, goza 20 depois do concessivo: o abono segue simples."""
        emp, contract, alloc = self._caso(None, None)
        slip = self._recibo(emp, contract, alloc, date(2027, 2, 1), 20, abono=10)
        self.assertEqual(slip.l10n_br_dias_ferias_dobro, 20)
        self.assertAlmostEqualMoney(self._get_line_total(slip, "FERIAS_DOBRO"), 2400)
        self.assertAlmostEqualMoney(
            self._get_line_total(slip, "ABONO_PECUNIARIO"), 1200
        )

    def test_estrutura_de_ferias_tem_as_duas_regras(self):
        codigos = self.structure_ferias.rule_ids.mapped("code")
        self.assertIn("FERIAS_DOBRO", codigos)
        self.assertIn("ADICIONAL_FERIAS_DOBRO", codigos)

    def test_rescisao_segue_dobrando_o_vencido(self):
        """A dobra da rescisão não regride: período vencido além do concessivo."""
        emp, contract, alloc = self._caso(None, None)
        slip = self.env["hr.payslip"].create(
            {
                "name": "Rescisão",
                "employee_id": emp.id,
                "contract_id": contract.id,
                "struct_id": self.structure_rescisao.id,
                "date_from": date(2027, 2, 1),
                "date_to": date(2027, 2, 28),
                "l10n_br_tipo_rescisao": "pedido_demissao",
                "l10n_br_aviso_previo": "nao_aplicavel",
                "company_id": self.env.company.id,
            }
        )
        contract.date_end = date(2027, 2, 28)
        slip.compute_sheet()
        self.assertAlmostEqualMoney(self._get_line_total(slip, "FERIAS_VENCIDAS"), 7200)

    # -- integridade entre holerites -----------------------------------------

    def test_periodo_aquisitivo_com_recibo_confirmado_recusa_mudar_as_datas(self):
        emp, contract, alloc = self._caso(None, None)
        slip = self._recibo(emp, contract, alloc, date(2027, 2, 1), 10)
        slip.action_payslip_done()
        with self.assertRaises(UserError):
            alloc.write({"date_to": date(2026, 6, 30)})

    def test_recibo_aberto_recalcula_com_a_nova_data(self):
        emp, contract, alloc = self._caso(None, None)
        slip = self._recibo(emp, contract, alloc, date(2027, 2, 1), 10)
        self.assertEqual(slip.l10n_br_dias_ferias_dobro, 10)
        alloc.write({"date_to": date(2026, 6, 30)})  # concessivo até 2027-06-30
        slip.compute_sheet()
        self.assertEqual(slip.l10n_br_dias_ferias_dobro, 0)
        self.assertEqual(self._get_line_total(slip, "FERIAS_DOBRO"), 0)
