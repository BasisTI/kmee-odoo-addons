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

    def _recibo_abono(self, emp, alloc, dias):
        contract = emp.contract_id or self._create_contract(
            emp, wage=3000.0, date_start=date(2024, 1, 2)
        )
        return self.env["hr.payslip"].create(
            {
                "name": "Abono",
                "employee_id": emp.id,
                "contract_id": contract.id,
                "struct_id": self.structure_ferias.id,
                "date_from": date(2025, 3, 3),
                "date_to": date(2025, 3, 22),
                "l10n_br_ferias_allocation_id": alloc.id,
                "l10n_br_dias_periodo_gozado": 20,
                "l10n_br_dias_abono": dias,
                "company_id": self.env.company.id,
            }
        )

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
        a = self._aloca(emp, A_INI, A_FIM)
        self._ausencia(emp, date(2025, 3, 3), date(2025, 3, 22))  # 20 dias de A
        self._recibo_abono(emp, a, 10)  # os 10 dias vendidos, em recibo
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

    # -- r3: ordem de débito, sem transbordo, dado legado --------------------------

    C_INI, C_FIM = date(2026, 1, 2), date(2027, 1, 1)  # concessivo até 2028-01-01

    def _tres_periodos(self, emp):
        return (
            self._aloca(emp, A_INI, A_FIM),
            self._aloca(emp, B_INI, B_FIM),
            self._aloca(emp, self.C_INI, self.C_FIM),
        )

    def test_vencido_intacto_e_debitado_antes_do_periodo_seguinte(self):
        """Três períodos validados, A vencido e intacto: a ausência depois do
        concessivo de A debita A, com aviso de dobra (e não B)."""
        emp = self._create_employee()
        a, b, _c = self._tres_periodos(emp)
        leave = self._ausencia(emp, date(2026, 6, 1), date(2026, 6, 30))
        self.assertEqual(leave._l10n_br_periodo_da_ausencia(), a)
        self.assertIn("30 dia(s)", leave.l10n_br_aviso_dobro)
        self.assertIn("2026-01-01", leave.l10n_br_aviso_dobro)

    def test_b_com_pouco_saldo_e_a_intacto_debita_a_e_nao_c(self):
        """Três períodos, A intacto: em dez/2026 a ausência debita A (o vencido
        mais antigo com saldo), nem B (abono de 10 dias lançado) nem C (cujo
        aquisitivo ainda está em curso)."""
        emp = self._create_employee()
        a, b, _c = self._tres_periodos(emp)
        self._recibo_abono(emp, b, 10)
        leave = self._ausencia(emp, date(2026, 12, 1), date(2026, 12, 20))
        self.assertEqual(leave._l10n_br_periodo_da_ausencia(), a)
        self.assertTrue(leave.l10n_br_aviso_dobro)

    def test_sem_c_aceita_debitando_a(self):
        emp = self._create_employee()
        a = self._aloca(emp, A_INI, A_FIM)
        self._aloca(emp, B_INI, B_FIM)
        leave = self._ausencia(emp, date(2026, 12, 1), date(2026, 12, 20))
        self.assertEqual(leave.state, "validate")
        self.assertEqual(leave._l10n_br_periodo_da_ausencia(), a)
        self.assertTrue(leave.l10n_br_aviso_dobro)

    def test_a_esgotado_o_proximo_vencido_com_saldo_e_debitado(self):
        """A esgotado em 2025: a ausência de dez/2026 debita B (o vencido mais
        antigo com saldo), com dobra, e não C."""
        emp = self._create_employee()
        a, b, _c = self._tres_periodos(emp)
        self._ausencia(emp, date(2025, 3, 3), date(2025, 4, 1))  # 30 dias de A
        leave = self._ausencia(emp, date(2027, 2, 1), date(2027, 2, 10))
        self.assertEqual(leave._l10n_br_periodo_da_ausencia(), b)
        self.assertTrue(leave.l10n_br_aviso_dobro)

    def test_sem_vencido_com_saldo_debita_o_periodo_do_concessivo(self):
        emp = self._create_employee()
        self._aloca(emp, A_INI, A_FIM)
        self._ausencia(emp, date(2025, 3, 3), date(2025, 4, 1))  # A esgotado
        b = self._aloca(emp, B_INI, B_FIM)
        leave = self._ausencia(emp, date(2026, 3, 2), date(2026, 3, 11))
        self.assertEqual(leave._l10n_br_periodo_da_ausencia(), b)
        self.assertFalse(leave.l10n_br_aviso_dobro)

    def test_ausencia_nao_transborda_para_o_periodo_seguinte(self):
        """20 dias com 10 de saldo no período: recusada, com o saldo na mensagem."""
        emp = self._create_employee()
        self._aloca(emp, A_INI, A_FIM)
        self._ausencia(emp, date(2025, 3, 3), date(2025, 3, 22))  # 20 dias; sobram 10
        self._aloca(emp, B_INI, B_FIM)
        with self.assertRaises(ValidationError) as erro:
            self._ausencia(emp, date(2026, 3, 2), date(2026, 3, 21))  # 20 dias
        self.assertIn("tem 10 dia(s) de saldo", str(erro.exception))
        # o resto vai noutra ausência: 10 dias de A cabem
        leave = self._ausencia(emp, date(2026, 3, 2), date(2026, 3, 11))
        self.assertEqual(leave.state, "validate")

    def test_nunca_debita_periodo_cujo_aquisitivo_nao_terminou(self):
        """CLT art. 134: ausência antes do fim do aquisitivo é recusada."""
        emp = self._create_employee()
        self._aloca(emp, B_INI, B_FIM)
        with self.assertRaises(ValidationError):
            self._ausencia(emp, date(2025, 11, 17), date(2025, 11, 21))

    def test_dado_legado_acima_do_direito_nao_bloqueia_outro_periodo(self):
        """A foi gozado por inteiro (30 dias) e depois perde direito por faltas
        (24 dias): o dado de A fica acima do direito. Isso não barra uma ausência
        que debita B."""
        emp = self._create_employee()
        a = self._aloca(emp, A_INI, A_FIM)
        self._ausencia(emp, date(2025, 3, 3), date(2025, 4, 1))  # 30 dias de A
        a.write({"l10n_br_faltas_periodo_aquisitivo": 10})  # direito de 24
        self.assertEqual(a.number_of_days, 24)
        self._aloca(emp, B_INI, B_FIM)
        leave = self._ausencia(emp, date(2026, 3, 2), date(2026, 3, 11))
        self.assertEqual(leave.state, "validate")
        self.assertNotEqual(leave._l10n_br_periodo_da_ausencia(), a)

    def test_ausencia_ja_paga_debita_o_periodo_do_recibo(self):
        """A ausência com recibo de férias debita o período do recibo (escolha
        explícita), não o mais antigo: a seguinte pode debitar o antigo."""
        emp = self._create_employee()
        a = self._aloca(emp, A_INI, A_FIM)
        b = self._aloca(emp, B_INI, B_FIM)
        contract = self._create_contract(emp, wage=3000.0, date_start=date(2024, 1, 2))
        self._ausencia(emp, date(2026, 11, 1), date(2026, 11, 20))  # sem recibo: A
        antes = self.env["hr.leave"].search([("employee_id", "=", emp.id)])
        self.assertEqual(antes._l10n_br_periodo_da_ausencia(), a)
        self.env["hr.payslip"].create(
            {
                "name": "Férias",
                "employee_id": emp.id,
                "contract_id": contract.id,
                "struct_id": self.structure_ferias.id,
                "date_from": date(2026, 11, 1),
                "date_to": date(2026, 11, 20),
                "l10n_br_ferias_allocation_id": b.id,
                "l10n_br_dias_periodo_gozado": 20,
                "l10n_br_dias_abono": 10,
                "company_id": self.env.company.id,
            }
        )
        # com o recibo de B, a ausência passa a debitar B (20 + 10 de abono = 30)
        leave = self._ausencia(emp, date(2026, 12, 1), date(2026, 12, 20))
        self.assertEqual(leave._l10n_br_periodo_da_ausencia(), a)
        self.assertEqual(leave.state, "validate")

    # -- r4: uma fonte só decide o período (validade, aviso, redistribuição) ---------

    def _recibo_ferias(self, emp, alloc, inicio, fim, dias, abono=0):
        contract = emp.contract_id or self._create_contract(
            emp, wage=3000.0, date_start=A_INI
        )
        slip = self.env["hr.payslip"].create(
            {
                "name": "Férias",
                "employee_id": emp.id,
                "contract_id": contract.id,
                "struct_id": self.structure_ferias.id,
                "date_from": inicio,
                "date_to": fim,
                "l10n_br_ferias_allocation_id": alloc.id,
                "l10n_br_dias_periodo_gozado": dias,
                "l10n_br_dias_abono": abono,
                "company_id": self.env.company.id,
            }
        )
        slip.compute_sheet()
        return slip

    def test_vencido_em_dobro_e_depois_o_periodo_seguinte_sem_o_posterior(self):
        """A e B validados: a ausência de A em dobro e depois a de B são aceitas
        (o hr_holidays não barra o período seguinte)."""
        emp = self._create_employee()
        a = self._aloca(emp, A_INI, A_FIM)
        b = self._aloca(emp, B_INI, B_FIM)
        primeira = self._ausencia(emp, date(2026, 3, 2), date(2026, 3, 31))
        self.assertEqual(primeira._l10n_br_periodo_da_ausencia(), a)
        segunda = self._ausencia(emp, date(2026, 6, 1), date(2026, 6, 30))
        self.assertEqual(segunda.state, "validate")
        self.assertEqual(segunda._l10n_br_periodo_da_ausencia(), b)
        self.assertFalse(segunda.l10n_br_aviso_dobro)

    def test_tres_periodos_com_ausencias_em_2027(self):
        """A, B e C completos (sem o hr_holidays barrar): cada ausência debita o
        vencido mais antigo com saldo, num só período."""
        emp = self._create_employee()
        a, b, c = self._tres_periodos(emp)
        casos = (
            (date(2027, 3, 1), date(2027, 3, 25), a),  # 25 dias; A fica com 5
            (date(2027, 4, 1), date(2027, 4, 5), a),  # 5 dias; A esgotado
            (date(2027, 5, 3), date(2027, 5, 27), b),  # 25 dias; B fica com 5
            (date(2027, 8, 2), date(2027, 8, 6), b),  # 5 dias; B esgotado
            (date(2027, 10, 4), date(2027, 10, 28), c),  # 25 dias de C
        )
        for inicio, fim, periodo in casos:
            leave = self._ausencia(emp, inicio, fim)
            self.assertEqual(leave.state, "validate", inicio)
            self.assertEqual(leave._l10n_br_periodo_da_ausencia(), periodo, inicio)

    def test_ausencia_paga_em_recibo_de_b_tem_aviso_do_periodo_de_b(self):
        """O aviso usa a mesma análise da restrição, com o período do recibo."""
        emp = self._create_employee()
        a = self._aloca(emp, A_INI, A_FIM)
        b = self._aloca(emp, B_INI, B_FIM)
        leave = self._ausencia(emp, date(2026, 11, 1), date(2026, 11, 20))
        self.assertEqual(leave._l10n_br_periodo_da_ausencia(), a)
        self._recibo_ferias(emp, b, date(2026, 11, 1), date(2026, 11, 20), 20, abono=10)
        leave.invalidate_recordset()
        self.assertEqual(leave._l10n_br_periodo_da_ausencia(), b)
        self.assertFalse(leave.l10n_br_aviso_dobro)  # B ainda está no concessivo

    def test_recusar_uma_ausencia_redistribui_o_aviso_das_seguintes(self):
        emp = self._create_employee()
        a, b, _c = self._tres_periodos(emp)
        l1 = self._ausencia(emp, date(2026, 3, 2), date(2026, 3, 21))  # 20 de A
        self._ausencia(emp, date(2026, 6, 1), date(2026, 6, 10))  # 10 de A
        l3 = self._ausencia(emp, date(2026, 9, 1), date(2026, 9, 25))  # 25 de B
        self.assertEqual(l3._l10n_br_periodo_da_ausencia(), b)
        notas = len(l3.message_ids)
        l1.action_refuse()
        # sem l1, A tem 20 de saldo e a de 25 dias vai para A, com 5 de excesso
        self.assertEqual(l3._l10n_br_periodo_da_ausencia(), a)
        self.assertEqual(l3.state, "validate")  # a ausência já lançada fica
        self.assertIn("5 dia(s) do saldo", l3.l10n_br_aviso_dobro)
        self.assertGreater(len(l3.message_ids), notas)

    def test_recibo_posterior_corrige_a_nota_de_dobra_falsa(self):
        """A ausência nasce antes do recibo e a nota de dobra sai (debita A, o mais
        antigo); o recibo de B fixa o período e a nota é retratada."""
        emp = self._create_employee()
        self._aloca(emp, A_INI, A_FIM)
        b = self._aloca(emp, B_INI, B_FIM)
        leave = self._ausencia(emp, date(2026, 11, 1), date(2026, 11, 20))
        self.assertTrue(leave.l10n_br_aviso_notificado)  # dobra de A
        self._recibo_ferias(emp, b, date(2026, 11, 1), date(2026, 11, 20), 20, abono=10)
        self.assertFalse(leave.l10n_br_aviso_notificado)
        corpos = leave.message_ids.mapped("body")
        self.assertTrue(any("não vale mais" in (c or "") for c in corpos))
