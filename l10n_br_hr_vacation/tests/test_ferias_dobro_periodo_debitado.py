# Copyright 2026 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""TG-139 r2: o período que a ausência de férias debita (revisão r1).

O tipo Férias conta dias úteis no ``hr_holidays`` e o abono não vira ausência:
a sobra do período antigo, em dias úteis, não é saldo de férias e não pode
absorver as férias do período corrente nem gerar aviso de dobra. O concessivo
segue como limite normal; o período vencido só é debitado quando nenhum
concessivo cobre a ausência, e só com saldo real, em dias corridos.
"""
from datetime import date

from odoo.exceptions import UserError, ValidationError
from odoo.tests import tagged

from .common import VacationCommon

A_INI, A_FIM = date(2024, 1, 2), date(2025, 1, 1)  # concessivo até 2026-01-01
B_INI, B_FIM = date(2025, 1, 2), date(2026, 1, 1)  # concessivo até 2027-01-01


@tagged("post_install", "-at_install")
class TestFeriasDobroPeriodoDebitado(VacationCommon):
    def _aloca(self, emp, de, ate, **extra):
        alloc = self.env["hr.leave.allocation"].create(
            dict(
                {
                    "employee_id": emp.id,
                    "holiday_status_id": self.leave_type_ferias.id,
                    "date_from": de,
                    "date_to": ate,
                },
                **extra,
            )
        )
        alloc.action_validate()
        return alloc

    def _ausencia(self, emp, inicio, fim):
        leave = self.env["hr.leave"].create(
            {
                "employee_id": emp.id,
                "holiday_status_id": self.leave_type_ferias.id,
                "request_date_from": inicio,
                "request_date_to": fim,
            }
        )
        leave.action_validate()
        return leave

    def test_periodo_anterior_todo_gozado_nao_gera_aviso_falso(self):
        """A gozado por inteiro no concessivo; a ausência de B no concessivo de B."""
        emp = self._create_employee()
        self._aloca(emp, A_INI, A_FIM)
        self._ausencia(emp, date(2025, 3, 3), date(2025, 4, 1))  # 30 dias de A
        self._aloca(emp, B_INI, B_FIM)
        leave = self._ausencia(emp, date(2026, 3, 2), date(2026, 3, 11))
        self.assertFalse(leave.l10n_br_aviso_dobro)
        self.assertFalse(leave.message_ids.filtered(lambda m: "dobro" in m.body))

    def test_sobra_do_abono_nao_e_consumida_pelo_periodo_seguinte(self):
        """A: 20 dias gozados e 10 de abono (sem ausência); B: ausências depois do
        concessivo de A, dentro do de B. B não passa dos 30 dias corridos."""
        emp = self._create_employee()
        self._aloca(emp, A_INI, A_FIM)
        self._ausencia(emp, date(2025, 3, 3), date(2025, 3, 22))  # 20 dias de A
        self._aloca(emp, B_INI, B_FIM)
        leave = self._ausencia(emp, date(2026, 3, 2), date(2026, 3, 11))  # 10 dias
        self.assertFalse(leave.l10n_br_aviso_dobro)
        with self.assertRaises(ValidationError):
            self._ausencia(emp, date(2026, 6, 1), date(2026, 6, 30))  # +30 > 30

    def test_ausencia_de_30_dias_corridos_consome_30_do_direito(self):
        emp = self._create_employee()
        self._aloca(emp, B_INI, B_FIM)
        self._ausencia(emp, date(2026, 3, 2), date(2026, 3, 31))  # 30 corridos
        with self.assertRaises(ValidationError):
            self._ausencia(emp, date(2026, 11, 2), date(2026, 11, 3))

    def test_dobra_de_periodo_vencido_so_com_saldo_real(self):
        """Depois de todos os concessivos, o vencido mais antigo COM saldo: A está
        todo gozado, então a ausência debita B e o aviso conta do concessivo de B."""
        emp = self._create_employee()
        self._aloca(emp, A_INI, A_FIM)
        self._ausencia(emp, date(2025, 3, 3), date(2025, 4, 1))  # 30 dias de A
        self._aloca(emp, B_INI, B_FIM)
        leave = self._ausencia(emp, date(2027, 3, 1), date(2027, 3, 10))
        self.assertIn("10 dia(s)", leave.l10n_br_aviso_dobro)
        self.assertIn("2027-01-01", leave.l10n_br_aviso_dobro)

    def test_aviso_so_dos_dias_depois_do_concessivo_do_periodo_debitado(self):
        emp = self._create_employee()
        self._aloca(emp, B_INI, B_FIM)
        leave = self._ausencia(emp, date(2026, 12, 28), date(2027, 1, 10))
        self.assertIn("9 dia(s)", leave.l10n_br_aviso_dobro)

    def test_prescricao_do_art_149_avisa_e_nao_bloqueia(self):
        """Período de 2017 lançado em 2026: aceito, com os dois avisos."""
        emp = self._create_employee()
        self._aloca(emp, date(2017, 1, 2), date(2018, 1, 1))
        leave = self._ausencia(emp, date(2026, 3, 2), date(2026, 3, 31))
        self.assertEqual(leave.state, "validate")
        self.assertIn("dobro", leave.l10n_br_aviso_dobro)
        self.assertIn("prescrita", leave.l10n_br_aviso_prescricao)
        self.assertTrue(
            leave.message_ids.filtered(lambda m: "prescrita" in m.body),
        )

    def test_dobra_recente_nao_avisa_prescricao(self):
        emp = self._create_employee()
        self._aloca(emp, B_INI, B_FIM)
        leave = self._ausencia(emp, date(2027, 3, 1), date(2027, 3, 5))
        self.assertTrue(leave.l10n_br_aviso_dobro)
        self.assertFalse(leave.l10n_br_aviso_prescricao)

    # -- faltas e datas com recibo confirmado -----------------------------------

    def _recibo_confirmado(self, emp, alloc):
        contract = self._create_contract(emp, wage=3000.0, date_start=date(2024, 1, 2))
        slip = self.env["hr.payslip"].create(
            {
                "name": "Férias",
                "employee_id": emp.id,
                "contract_id": contract.id,
                "struct_id": self.structure_ferias.id,
                "date_from": date(2025, 12, 23),
                "date_to": date(2026, 1, 21),
                "l10n_br_ferias_allocation_id": alloc.id,
                "l10n_br_dias_periodo_gozado": 30,
                "company_id": self.env.company.id,
            }
        )
        slip.compute_sheet()
        slip.action_payslip_done()
        return slip

    def test_mudar_faltas_com_recibo_confirmado_e_recusado(self):
        emp = self._create_employee()
        alloc = self._aloca(emp, A_INI, A_FIM)
        self._recibo_confirmado(emp, alloc)
        with self.assertRaises(UserError):
            alloc.write({"l10n_br_faltas_periodo_aquisitivo": 10})
        self.assertEqual(alloc.number_of_days, 30)

    def test_mudar_faltas_sem_recibo_confirmado_continua_permitido(self):
        emp = self._create_employee()
        alloc = self._aloca(emp, A_INI, A_FIM)
        alloc.write({"l10n_br_faltas_periodo_aquisitivo": 10})
        self.assertEqual(alloc.number_of_days, 24)
