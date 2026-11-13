# Copyright 2026 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""Férias de período aquisitivo vencido, dentro do concessivo (TG-95).

CLT art. 134: as férias são concedidas nos 12 meses seguintes ao fim do
período aquisitivo (período concessivo). O ``hr_holidays`` valida a ausência
contra a alocação até ``date_to`` (o fim do aquisitivo) e recusava as férias
gozadas no concessivo ("Você não possui nenhuma alocação"). A POC contornava
com um segundo saldo sem data final.
"""
from datetime import date

from odoo.exceptions import ValidationError
from odoo.tests import tagged

from .common import VacationCommon

AQ_INI, AQ_FIM = date(2025, 1, 2), date(2026, 1, 1)  # concessivo até 2027-01-01


@tagged("post_install", "-at_install")
class TestFeriasPeriodoVencido(VacationCommon):
    def _aloca(self, emp, de=AQ_INI, ate=AQ_FIM):
        alloc = self.env["hr.leave.allocation"].create(
            {
                "employee_id": emp.id,
                "holiday_status_id": self.leave_type_ferias.id,
                "date_from": de,
                "date_to": ate,
            }
        )
        alloc.action_validate()
        return alloc

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

    def test_ferias_no_concessivo_sao_aceitas_sem_saldo_sem_data_final(self):
        emp = self._create_employee()
        self._aloca(emp)
        leave = self._ausencia(emp, date(2026, 11, 16), date(2026, 11, 25))
        self.assertEqual(leave.state, "validate")

    def test_ultimo_dia_do_concessivo_e_aceito(self):
        emp = self._create_employee()
        self._aloca(emp)
        leave = self._ausencia(emp, date(2026, 12, 28), date(2027, 1, 1))
        self.assertEqual(leave.state, "validate")

    def test_ferias_depois_do_concessivo_continuam_recusadas(self):
        """Depois do concessivo as férias são devidas em dobro (art. 137): a
        ausência não é aceita pelo saldo vencido."""
        emp = self._create_employee()
        self._aloca(emp)
        with self.assertRaises(ValidationError):
            self._ausencia(emp, date(2027, 2, 1), date(2027, 2, 5))

    def test_ferias_antes_do_inicio_do_aquisitivo_sao_recusadas(self):
        emp = self._create_employee()
        self._aloca(emp)
        with self.assertRaises(ValidationError):
            self._ausencia(emp, date(2024, 12, 2), date(2024, 12, 6))

    def test_sem_alocacao_continua_recusada(self):
        emp = self._create_employee()
        with self.assertRaises(ValidationError):
            self._ausencia(emp, date(2026, 11, 16), date(2026, 11, 25))

    def test_periodo_em_curso_continua_aceito(self):
        emp = self._create_employee()
        self._aloca(emp)
        leave = self._ausencia(emp, date(2025, 11, 17), date(2025, 11, 21))
        self.assertEqual(leave.state, "validate")

    def test_saldo_do_periodo_vencido_nao_e_excedido(self):
        """O concessivo estende a validade, não o saldo: 30 dias de direito."""
        emp = self._create_employee()
        self._aloca(emp)
        self._ausencia(emp, date(2026, 3, 2), date(2026, 3, 31))  # 22 dias úteis
        with self.assertRaises(ValidationError):
            self._ausencia(emp, date(2026, 11, 2), date(2026, 11, 30))

    def test_dois_periodos_consomem_o_mais_antigo_primeiro(self):
        emp = self._create_employee()
        self._aloca(emp)
        self._aloca(emp, date(2026, 1, 2), date(2027, 1, 1))
        a = self._ausencia(emp, date(2026, 3, 2), date(2026, 3, 31))
        b = self._ausencia(emp, date(2026, 11, 2), date(2026, 11, 30))
        self.assertEqual((a.state, b.state), ("validate", "validate"))

    def test_recibo_usa_a_alocacao_do_periodo_vencido(self):
        emp = self._create_employee()
        contract = self._create_contract(emp, wage=3600.0, date_start=date(2024, 1, 2))
        alloc = self._aloca(emp)
        self._ausencia(emp, date(2026, 11, 16), date(2026, 11, 25))
        slip = self.env["hr.payslip"].create(
            {
                "name": "Férias nov/2026",
                "employee_id": emp.id,
                "contract_id": contract.id,
                "struct_id": self.structure_ferias.id,
                "date_from": date(2026, 11, 16),
                "date_to": date(2026, 11, 25),
                "l10n_br_ferias_allocation_id": alloc.id,
                "l10n_br_dias_periodo_gozado": 10,
                "company_id": self.env.company.id,
            }
        )
        slip.compute_sheet()
        self.assertAlmostEqualMoney(self._get_line_total(slip, "FERIAS"), 1200)
