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
from odoo.tests import Form, tagged

from .common import VacationCommon

AQ_INI, AQ_FIM = date(2025, 1, 2), date(2026, 1, 1)  # concessivo até 2027-01-01
EC_INI, EC_FIM = date(2026, 1, 2), date(2027, 1, 1)


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

    # -- ordem de criação: o total por alocação nunca passa do direito ---------

    def _total(self, *leaves):
        return sum(self.env["hr.leave"].concat(*leaves).mapped("number_of_days"))

    def test_fora_de_ordem_periodo_em_curso_estoura_o_saldo(self):
        emp = self._create_employee()
        self._aloca(emp, EC_INI, EC_FIM)
        self._ausencia(emp, date(2026, 11, 2), date(2026, 11, 30))  # 21 dias
        with self.assertRaises(ValidationError):
            self._ausencia(emp, date(2026, 3, 2), date(2026, 3, 31))  # +22 = 43/30

    def test_fora_de_ordem_periodo_vencido_estoura_o_saldo(self):
        emp = self._create_employee()
        self._aloca(emp)
        self._ausencia(emp, date(2026, 11, 2), date(2026, 11, 30))
        with self.assertRaises(ValidationError):
            self._ausencia(emp, date(2026, 3, 2), date(2026, 3, 31))

    def test_tres_fracoes_de_tras_para_frente(self):
        emp = self._create_employee()
        self._aloca(emp, EC_INI, EC_FIM)
        self._ausencia(emp, date(2026, 12, 1), date(2026, 12, 21))  # 15
        self._ausencia(emp, date(2026, 7, 1), date(2026, 7, 21))  # 15
        with self.assertRaises(ValidationError):
            self._ausencia(emp, date(2026, 3, 2), date(2026, 3, 20))  # +15 = 45/30

    def test_duas_alocacoes_fora_de_ordem(self):
        emp = self._create_employee()
        self._aloca(emp)
        self._aloca(emp, EC_INI, EC_FIM)
        self._ausencia(emp, date(2026, 3, 2), date(2026, 3, 31))  # 22
        self._ausencia(emp, date(2027, 2, 1), date(2027, 2, 26))  # 20
        with self.assertRaises(ValidationError):
            self._ausencia(emp, date(2026, 11, 2), date(2026, 11, 30))  # 63/60

    def test_ausencia_recusada_libera_o_saldo(self):
        emp = self._create_employee()
        self._aloca(emp)
        self._ausencia(emp, date(2026, 3, 2), date(2026, 3, 31)).action_refuse()
        leave = self._ausencia(emp, date(2026, 11, 2), date(2026, 11, 30))
        self.assertEqual(leave.state, "validate")

    def test_ausencia_que_cruza_o_fim_do_concessivo_e_recusada(self):
        """A parte depois do concessivo não tem saldo (dobra: art. 137)."""
        emp = self._create_employee()
        self._aloca(emp)
        with self.assertRaises(ValidationError):
            self._ausencia(emp, date(2026, 12, 28), date(2027, 1, 15))

    def test_outro_tipo_de_folga_nao_muda(self):
        emp = self._create_employee()
        tipo = self.env["hr.leave.type"].create(
            {"name": "Banco", "requires_allocation": "yes", "request_unit": "day"}
        )
        self.env["hr.leave.allocation"].create(
            {
                "employee_id": emp.id,
                "holiday_status_id": tipo.id,
                "date_from": AQ_INI,
                "date_to": AQ_FIM,
                "number_of_days": 30,
            }
        ).action_validate()
        with self.assertRaises(ValidationError):
            self.env["hr.leave"].create(
                {
                    "employee_id": emp.id,
                    "holiday_status_id": tipo.id,
                    "request_date_from": date(2026, 11, 2),
                    "request_date_to": date(2026, 11, 6),
                }
            )

    # -- tela: seletor, saldo e dias tomados ----------------------------------

    def _contexto_tela(self, emp, de="2026-11-16 11:00:00", ate="2026-11-25 20:00:00"):
        return {
            "employee_id": emp.id,
            "default_employee_id": emp.id,
            "default_date_from": de,
            "default_date_to": ate,
        }

    def _dominio_seletor(self):
        # o domínio do campo holiday_status_id da view de hr_holidays
        return [
            "|",
            ("requires_allocation", "=", "no"),
            "&",
            ("has_valid_allocation", "=", True),
            "|",
            ("allows_negative", "=", True),
            "&",
            ("virtual_remaining_leaves", ">", 0),
            ("allows_negative", "=", False),
        ]

    def test_seletor_da_tela_lista_ferias_no_concessivo(self):
        emp = self._create_employee()
        self._aloca(emp)
        tipos = (
            self.env["hr.leave.type"]
            .with_context(**self._contexto_tela(emp))
            .search(self._dominio_seletor())
        )
        self.assertIn(self.leave_type_ferias, tipos)

    def test_seletor_da_tela_nao_lista_ferias_depois_do_concessivo(self):
        emp = self._create_employee()
        self._aloca(emp)
        ctx = self._contexto_tela(emp, "2027-02-01 11:00:00", "2027-02-05 20:00:00")
        tipos = (
            self.env["hr.leave.type"]
            .with_context(**ctx)
            .search(self._dominio_seletor())
        )
        self.assertNotIn(self.leave_type_ferias, tipos)

    def test_seletor_da_tela_sem_saldo_nao_lista_ferias(self):
        emp = self._create_employee()
        self._aloca(emp)
        self._ausencia(emp, date(2026, 3, 2), date(2026, 4, 10))  # esgota os 30
        tipos = (
            self.env["hr.leave.type"]
            .with_context(**self._contexto_tela(emp))
            .search(self._dominio_seletor())
        )
        self.assertNotIn(self.leave_type_ferias, tipos)

    def test_saldo_exibido_e_dias_tomados_no_concessivo(self):
        emp = self._create_employee()
        alloc = self._aloca(emp)
        tipo = self.leave_type_ferias
        dados = tipo.get_allocation_data(emp, date(2026, 3, 2))[emp][0][1]
        self.assertEqual(dados["max_leaves"], 30)
        self.assertEqual(dados["virtual_remaining_leaves"], 30)
        leave = self._ausencia(emp, date(2026, 3, 2), date(2026, 3, 13))
        alloc.invalidate_recordset()
        dados = tipo.get_allocation_data(emp, date(2026, 3, 2))[emp][0][1]
        self.assertFalse(dados["virtual_excess_data"])
        self.assertEqual(dados["virtual_leaves_taken"], leave.number_of_days)
        self.assertEqual(dados["virtual_remaining_leaves"], 30 - leave.number_of_days)
        # "dias tomados" da alocação (o hr_holidays conta até hoje: a ausência
        # de março já passou e a alocação venceu em 01/01/2026).
        alloc.invalidate_recordset()
        self.assertEqual(alloc.leaves_taken, leave.number_of_days)

    def test_form_da_tela_aceita_ferias_no_concessivo(self):
        emp = self._create_employee()
        self._aloca(emp)
        form = Form(self.env["hr.leave"].with_context(default_employee_id=emp.id))
        form.holiday_status_id = self.leave_type_ferias
        form.request_date_from = date(2026, 12, 1)
        form.request_date_to = date(2026, 12, 4)
        self.assertEqual(form.save().holiday_status_id, self.leave_type_ferias)

    def test_date_to_da_alocacao_nao_muda(self):
        """O cache estendido do cálculo de saldo não vaza nem grava."""
        emp = self._create_employee()
        alloc = self._aloca(emp)
        self._ausencia(emp, date(2026, 11, 16), date(2026, 11, 25))
        self.leave_type_ferias.get_allocation_data(emp, date(2026, 11, 16))
        self.assertEqual(alloc.date_to, AQ_FIM)
        self.env.flush_all()
        self.env.cr.execute(
            "SELECT date_to FROM hr_leave_allocation WHERE id = %s", (alloc.id,)
        )
        self.assertEqual(self.env.cr.fetchone()[0], AQ_FIM)
