# Copyright 2024 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""Proporcionalidade do salário: admissão, desligamento e afastamento (TG-82).

Casos de referência: gabarito da POC (P009, P010, P011), outubro/2026.
"""
from datetime import date

from odoo.tests.common import BaseCase

from ..models.salary_rules_br import dias_salario_mes
from .common import PayrollCommon

OUT_INI, OUT_FIM = date(2026, 10, 1), date(2026, 10, 31)


class TestDiasSalarioMes(BaseCase):
    """Função pura: dias de salário no mês comercial de 30 dias."""

    def test_mes_cheio_e_30(self):
        self.assertEqual(dias_salario_mes(OUT_INI, OUT_FIM), 30)

    def test_fevereiro_cheio_e_30(self):
        self.assertEqual(dias_salario_mes(date(2026, 2, 1), date(2026, 2, 28)), 30)

    def test_admissao_em_15_10_paga_17_dias(self):
        self.assertEqual(
            dias_salario_mes(OUT_INI, OUT_FIM, data_admissao=date(2026, 10, 15)), 17
        )

    def test_desligamento_em_20_10_paga_20_dias(self):
        self.assertEqual(
            dias_salario_mes(OUT_INI, OUT_FIM, data_demissao=date(2026, 10, 20)), 20
        )

    def test_afastamento_5_a_26_10_desconta_7_dias_do_inss(self):
        """22 dias de afastamento: 15 da empresa, 7 do INSS."""
        self.assertEqual(
            dias_salario_mes(
                OUT_INI,
                OUT_FIM,
                afastamentos_inss=[(date(2026, 10, 5), date(2026, 10, 26))],
            ),
            23,
        )

    def test_afastamento_ate_15_dias_nao_desconta(self):
        self.assertEqual(
            dias_salario_mes(
                OUT_INI,
                OUT_FIM,
                afastamentos_inss=[(date(2026, 10, 5), date(2026, 10, 19))],
            ),
            30,
        )

    def test_afastamento_iniciado_no_mes_anterior(self):
        """Início em 20/09: o 16º dia é 05/10; de 05 a 10/10 são 6 dias do INSS."""
        self.assertEqual(
            dias_salario_mes(
                OUT_INI,
                OUT_FIM,
                afastamentos_inss=[(date(2026, 9, 20), date(2026, 10, 10))],
            ),
            24,
        )

    def test_contrato_fora_do_periodo(self):
        self.assertEqual(
            dias_salario_mes(OUT_INI, OUT_FIM, data_demissao=date(2026, 9, 30)), 0
        )


class TestSalarioProporcional(PayrollCommon):
    """Holerite de 10/2026 com contrato iniciado, encerrado ou afastado no mês."""

    def _holerite(self, wage, date_start, date_end=None, **extra):
        emp = self._create_employee()
        contract = self._create_contract(emp, wage=wage, date_start=date_start)
        if date_end:
            contract.date_end = date_end
        if extra.get("periculosidade"):
            contract.l10n_br_periculosidade = True
        return emp, contract, self._create_payslip(emp, contract, OUT_INI, OUT_FIM)

    def test_admissao_no_meio_do_mes(self):
        _emp, _c, slip = self._holerite(6000.0, date(2026, 10, 15))
        self.assertAlmostEqualMoney(self._get_line_total(slip, "SALARIO_BASE"), 3400.0)
        self.assertAlmostEqualMoney(self._get_line_total(slip, "GROSS"), 3400.0)

    def test_desligamento_no_meio_do_mes(self):
        _emp, _c, slip = self._holerite(5000.0, date(2023, 1, 2), date(2026, 10, 20))
        self.assertAlmostEqualMoney(self._get_line_total(slip, "SALARIO_BASE"), 3333.33)

    def test_mes_cheio_inalterado(self):
        _emp, _c, slip = self._holerite(5000.0, date(2023, 1, 2))
        self.assertAlmostEqualMoney(self._get_line_total(slip, "SALARIO_BASE"), 5000.0)

    def test_periculosidade_acompanha_os_dias(self):
        _emp, _c, slip = self._holerite(6000.0, date(2026, 10, 15), periculosidade=True)
        self.assertAlmostEqualMoney(
            self._get_line_total(slip, "ADICIONAL_PERICULOSIDADE"), 1020.0
        )

    def test_afastamento_por_doenca_acima_de_15_dias(self):
        tipo = self.env["hr.leave.type"].create(
            {
                "name": "Afastamento por doença (teste)",
                "requires_allocation": "no",
                "leave_validation_type": "no_validation",
                "l10n_br_afastamento_inss": True,
            }
        )
        emp = self._create_employee()
        contract = self._create_contract(emp, wage=5500.0, date_start=date(2022, 8, 1))
        leave = self.env["hr.leave"].create(
            {
                "employee_id": emp.id,
                "holiday_status_id": tipo.id,
                "request_date_from": date(2026, 10, 5),
                "request_date_to": date(2026, 10, 26),
            }
        )
        if leave.state != "validate":
            leave.sudo().action_validate()
        slip = self._create_payslip(emp, contract, OUT_INI, OUT_FIM)
        self.assertAlmostEqualMoney(self._get_line_total(slip, "SALARIO_BASE"), 4216.67)
