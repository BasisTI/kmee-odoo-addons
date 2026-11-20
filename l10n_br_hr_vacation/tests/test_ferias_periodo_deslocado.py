# Copyright 2026 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""TG-160: período deslocado, alocações sobrepostas e trava da alocação usada.

Admissão em 15/01/2023, salário 3.000,00, períodos aquisitivos a partir de 20/01
(deslocados do aniversário), dispensa em 31/12/2025 com aviso indenizado de 33
dias (projeção até 02/02/2026). O período de 20/01/2025 a 19/01/2026 se completa
na projeção e precisa da própria alocação.
"""
from datetime import date

from odoo.exceptions import UserError
from odoo.tests import tagged

from .common import VacationCommon

SALARIO = 3000.0
ANTERIOR = (date(2024, 1, 20), date(2025, 1, 19))
DEVIDO = (date(2025, 1, 20), date(2026, 1, 19))
DESLIGAMENTO = date(2025, 12, 31)


@tagged("post_install", "-at_install")
class TestFeriasPeriodoDeslocado(VacationCommon):
    exigir_alocacao_periodo = True

    def _contrato(self):
        emp = self._create_employee()
        contract = self._create_contract(
            emp, wage=SALARIO, date_start=date(2023, 1, 15)
        )
        return emp, contract

    def _alocacao(self, emp, periodo):
        alloc = self.env["hr.leave.allocation"].create(
            {
                "employee_id": emp.id,
                "holiday_status_id": self.leave_type_ferias.id,
                "date_from": periodo[0],
                "date_to": periodo[1],
            }
        )
        alloc.action_validate()
        return alloc

    def _rescisao(self, emp, contract, desligamento=DESLIGAMENTO):
        contract.date_end = desligamento
        slip = self.env["hr.payslip"].create(
            {
                "name": "TG-160",
                "employee_id": emp.id,
                "contract_id": contract.id,
                "struct_id": self.structure_rescisao.id,
                "date_from": desligamento.replace(day=1),
                "date_to": desligamento,
                "l10n_br_tipo_rescisao": "sem_justa_causa",
                "l10n_br_aviso_previo": "indenizado",
                "company_id": self.env.company.id,
            }
        )
        slip.compute_sheet()
        return slip

    def _recusa(self, emp, contract, regex, desligamento=DESLIGAMENTO):
        with self.assertRaisesRegex(UserError, regex), self.env.cr.savepoint():
            self._rescisao(emp, contract, desligamento)

    # ---- 1. período deslocado ------------------------------------------------

    def test_deslocado_so_com_a_alocacao_do_periodo_anterior_recusa(self):
        emp, contract = self._contrato()
        self._alocacao(emp, ANTERIOR)
        self._recusa(emp, contract, "15/01/2025 a 14/01/2026")

    def test_deslocado_com_a_alocacao_do_periodo_devido_calcula(self):
        for anterior, periodo in (
            (ANTERIOR, DEVIDO),
            (
                (date(2024, 1, 16), date(2025, 1, 15)),
                (date(2025, 1, 16), date(2026, 1, 15)),
            ),
        ):
            emp, contract = self._contrato()
            self._alocacao(emp, anterior)
            self._alocacao(emp, periodo)
            slip = self._rescisao(emp, contract)
            self.assertEqual(len(slip._l10n_br_ferias_vencidas_dados()), 2, periodo)
            self.assertEqual(
                self._get_line_total(slip, "FERIAS_VENCIDAS"), 6000.0, periodo
            )

    def test_deslocado_so_com_a_alocacao_do_periodo_devido_calcula(self):
        emp, contract = self._contrato()
        self._alocacao(emp, DEVIDO)
        slip = self._rescisao(emp, contract)
        self.assertEqual(self._get_line_total(slip, "FERIAS_VENCIDAS"), 3000.0)

    def test_limite_um_ano_antes_da_projecao(self):
        """Aviso de 36 dias (2 anos completos): projeção até 05/02/2026. O que
        termina em 05/02/2025 (referência − 1 ano) é o período anterior; um dia
        depois já é o que fecha na projeção."""
        emp, contract = self._contrato()
        self._alocacao(emp, (date(2024, 2, 6), date(2025, 2, 5)))
        self._recusa(emp, contract, "projeção do aviso")
        emp2, contract2 = self._contrato()
        self._alocacao(emp2, (date(2024, 2, 7), date(2025, 2, 6)))
        self._rescisao(emp2, contract2)

    # ---- 2. alocações sobrepostas --------------------------------------------

    def test_alocacoes_sobrepostas_do_mesmo_periodo_recusam_e_listam(self):
        emp, contract = self._contrato()
        a = self._alocacao(emp, (date(2025, 1, 15), date(2026, 1, 14)))
        b = self._alocacao(emp, DEVIDO)
        with self.assertRaises(UserError) as cm, self.env.cr.savepoint():
            self._rescisao(emp, contract)
        mensagem = cm.exception.args[0]
        for dado in ("15/01/2025", "14/01/2026", "20/01/2025", "19/01/2026"):
            self.assertIn(dado, mensagem)
        self.assertIn("id %s" % a.id, mensagem)
        self.assertIn("id %s" % b.id, mensagem)
        # recusada a duplicada, a rescisão calcula e paga uma vez só
        b.action_refuse()
        slip = self._rescisao(emp, contract)
        self.assertEqual(self._get_line_total(slip, "FERIAS_VENCIDAS"), 3000.0)

    def test_sobreposicao_de_periodo_antigo_tambem_recusa(self):
        emp, contract = self._contrato()
        self._alocacao(emp, (date(2024, 1, 15), date(2025, 1, 14)))
        self._alocacao(emp, ANTERIOR)
        self._alocacao(emp, DEVIDO)
        self._recusa(emp, contract, "mesmo período aquisitivo")

    def test_periodos_consecutivos_nao_se_sobrepoem(self):
        """date_to de um na véspera do date_from do outro: períodos distintos."""
        emp, contract = self._contrato()
        self._alocacao(emp, ANTERIOR)
        self._alocacao(emp, DEVIDO)
        slip = self._rescisao(emp, contract)
        self.assertEqual(self._get_line_total(slip, "FERIAS_VENCIDAS"), 6000.0)

    def test_sobrepostas_de_conjunto_so_acusa_intervalos_que_se_cruzam(self):
        emp, _contract = self._contrato()
        a = self._alocacao(emp, ANTERIOR)
        b = self._alocacao(emp, DEVIDO)
        self.assertFalse((a | b)._l10n_br_sobrepostas())
        c = self._alocacao(emp, (date(2025, 1, 19), date(2026, 1, 18)))
        self.assertEqual(len((a | b | c)._l10n_br_sobrepostas()), 2)

    # ---- 3. trava da alocação usada ------------------------------------------

    def test_alocacao_usada_por_rescisao_confirmada_recusa_vinculo_e_arquivo(self):
        emp, contract = self._contrato()
        outro = self._create_employee()
        aloc = self._alocacao(emp, DEVIDO)
        outro_tipo = self.env["hr.leave.type"].search(
            [("id", "!=", self.leave_type_ferias.id)], limit=1
        )
        slip = self._rescisao(emp, contract)
        slip.action_payslip_done()
        for vals in (
            {"employee_id": outro.id},
            {"holiday_status_id": outro_tipo.id},
            {"active": False},
        ):
            with self.assertRaisesRegex(UserError, "rescisão confirmada"):
                with self.env.cr.savepoint():
                    aloc.write(vals)
        self.assertEqual(aloc.employee_id, emp)
        self.assertEqual(aloc.holiday_status_id, self.leave_type_ferias)

    def test_alocacao_de_rescisao_aberta_aceita_trocar_o_empregado(self):
        emp, contract = self._contrato()
        outro = self._create_employee()
        aloc = self._alocacao(emp, DEVIDO)
        self._rescisao(emp, contract)
        aloc.write({"employee_id": outro.id})
        self.assertEqual(aloc.employee_id, outro)

    def test_alocacao_de_outro_empregado_nao_e_travada(self):
        emp, contract = self._contrato()
        self._alocacao(emp, DEVIDO)
        slip = self._rescisao(emp, contract)
        slip.action_payslip_done()
        outro = self._create_employee()
        alheia = self._alocacao(outro, DEVIDO)
        alheia.action_refuse()
        self.assertEqual(alheia.state, "refuse")

    def test_mover_alocacao_para_empregado_com_rescisao_confirmada_recusa(self):
        """A alocação de outro empregado, movida para quem tem rescisão
        confirmada que cobre o período, mudaria o que ela pagou."""
        emp, contract = self._contrato()
        self._alocacao(emp, DEVIDO)
        slip = self._rescisao(emp, contract)
        slip.action_payslip_done()
        alheia = self._alocacao(self._create_employee(), ANTERIOR)
        with self.assertRaisesRegex(UserError, "rescisão confirmada"):
            with self.env.cr.savepoint():
                alheia.write({"employee_id": emp.id})
