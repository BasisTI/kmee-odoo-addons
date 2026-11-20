# Copyright 2026 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""TG-165 r2: o vínculo vem do ``hr_contract`` (troca de contrato não é
readmissão), o período perdido não se goza nem se paga e a ausência debita só
as alocações do seu vínculo."""
from datetime import date

from odoo.exceptions import UserError, ValidationError
from odoo.tests import tagged

from .common import VacationCommon

SALARIO = 3000.0
DESLIGAMENTO = date(2025, 12, 31)


@tagged("post_install", "-at_install")
class TestFeriasVinculoArt133R2(VacationCommon):
    exigir_alocacao_periodo = True

    def _alocacao(self, emp, de, ate, **extra):
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

    def _rescisao(self, emp, contract):
        contract.date_end = DESLIGAMENTO
        slip = self.env["hr.payslip"].create(
            {
                "name": "TG-165 r2",
                "employee_id": emp.id,
                "contract_id": contract.id,
                "struct_id": self.structure_rescisao.id,
                "date_from": DESLIGAMENTO.replace(day=1),
                "date_to": DESLIGAMENTO,
                "l10n_br_tipo_rescisao": "sem_justa_causa",
                "l10n_br_aviso_previo": "indenizado",
                "company_id": self.env.company.id,
            }
        )
        slip.compute_sheet()
        return slip

    def _recibo(self, emp, contract, alloc):
        return self.env["hr.payslip"].create(
            {
                "name": "recibo",
                "employee_id": emp.id,
                "contract_id": contract.id,
                "struct_id": self.structure_ferias.id,
                "date_from": date(2025, 3, 3),
                "date_to": date(2025, 4, 1),
                "l10n_br_ferias_allocation_id": alloc.id,
                "l10n_br_dias_periodo_gozado": 30,
                "company_id": self.env.company.id,
            }
        )

    # ---- 1. vínculo = _get_first_contract_date(no_gap=True) ------------------

    def _anos(self, emp):
        self._alocacao(emp, date(2023, 1, 15), date(2024, 1, 14))
        self._alocacao(emp, date(2024, 1, 15), date(2025, 1, 14))
        self._alocacao(emp, date(2025, 1, 15), date(2026, 1, 14))

    def test_troca_de_contrato_sem_intervalo_nao_e_readmissao(self):
        """Experiência seguida de indeterminado no dia seguinte: um vínculo."""
        emp = self._create_employee()
        c1 = self._create_contract(emp, wage=SALARIO, date_start=date(2023, 1, 15))
        c1.write({"date_end": date(2023, 4, 14), "state": "close"})
        c2 = self._create_contract(emp, wage=SALARIO, date_start=date(2023, 4, 15))
        self._anos(emp)
        slip = self._rescisao(emp, c2)
        self.assertEqual(len(slip._l10n_br_ferias_vencidas_dados()), 3)
        self.assertEqual(self._get_line_total(slip, "FERIAS_VENCIDAS"), 12000.0)

    def test_readmissao_com_intervalo_separa_os_vinculos(self):
        emp = self._create_employee()
        c1 = self._create_contract(emp, wage=SALARIO, date_start=date(2020, 1, 1))
        c1.write({"date_end": date(2021, 12, 31), "state": "close"})
        c2 = self._create_contract(emp, wage=SALARIO, date_start=date(2023, 1, 15))
        self._alocacao(emp, date(2020, 1, 1), date(2020, 12, 31))
        self._alocacao(emp, date(2021, 1, 1), date(2021, 12, 31))
        self._alocacao(emp, date(2025, 1, 15), date(2026, 1, 14))
        slip = self._rescisao(emp, c2)
        self.assertEqual(len(slip._l10n_br_ferias_vencidas_dados()), 1)
        self.assertEqual(self._get_line_total(slip, "FERIAS_VENCIDAS"), 3000.0)

    def test_inicio_do_vinculo_ignora_contrato_posterior_e_cancelado(self):
        Alocacao = self.env["hr.leave.allocation"]
        emp = self._create_employee()
        cancelado = self._create_contract(
            emp, wage=SALARIO, date_start=date(2022, 12, 1)
        )
        cancelado.state = "cancel"
        c1 = self._create_contract(emp, wage=SALARIO, date_start=date(2023, 1, 15))
        c1.write({"date_end": date(2025, 12, 31), "state": "close"})
        c2 = self._create_contract(emp, wage=SALARIO, date_start=date(2026, 6, 1))
        self.assertEqual(
            Alocacao._l10n_br_inicio_do_vinculo(emp, c1), date(2023, 1, 15)
        )
        self.assertEqual(Alocacao._l10n_br_inicio_do_vinculo(emp, c2), date(2026, 6, 1))

    # ---- 2. período perdido não se goza nem se paga --------------------------

    def _com_perdido_sem_faltas(self, emp):
        self._alocacao(emp, date(2023, 1, 15), date(2024, 1, 14))
        return self._alocacao(
            emp, date(2024, 1, 15), date(2025, 1, 14), l10n_br_periodo_perdido=True
        )

    def test_recibo_de_ferias_recusa_periodo_perdido(self):
        """Afastamento acima de 6 meses (art. 133): sem faltas do art. 130."""
        emp = self._create_employee()
        c = self._create_contract(emp, wage=SALARIO, date_start=date(2023, 1, 15))
        perdida = self._com_perdido_sem_faltas(emp)
        with self.assertRaisesRegex(ValidationError, "perdido"):
            with self.env.cr.savepoint():
                self._recibo(emp, c, perdida)

    def test_marcar_alocacao_com_recibo_e_recusado(self):
        emp = self._create_employee()
        c = self._create_contract(emp, wage=SALARIO, date_start=date(2023, 1, 15))
        self._alocacao(emp, date(2023, 1, 15), date(2024, 1, 14))
        b = self._alocacao(emp, date(2024, 1, 15), date(2025, 1, 14))
        self._recibo(emp, c, b)
        with self.assertRaisesRegex(UserError, "já tem recibo"):
            with self.env.cr.savepoint():
                b.write({"l10n_br_periodo_perdido": True})

    def _max_leaves(self, emp):
        tipo = self.leave_type_ferias.with_context(employee_id=emp.id)
        dados = tipo.get_allocation_data(emp, date(2025, 3, 3))
        return sum(info["max_leaves"] for _n, info, _r, _i in dados.get(emp, []))

    def test_saldo_exibido_nao_conta_o_periodo_perdido(self):
        emp = self._create_employee()
        self._create_contract(emp, wage=SALARIO, date_start=date(2023, 1, 15))
        self._com_perdido_sem_faltas(emp)
        emp2 = self._create_employee()
        self._create_contract(emp2, wage=SALARIO, date_start=date(2023, 1, 15))
        self._alocacao(emp2, date(2023, 1, 15), date(2024, 1, 14))
        self.assertGreater(self._max_leaves(emp2), 0)
        self.assertEqual(self._max_leaves(emp), self._max_leaves(emp2))

    # ---- 3. ausência debita só o vínculo dela --------------------------------

    def _readmissao(self, com_contrato_anterior):
        emp = self._create_employee()
        if com_contrato_anterior:
            c1 = self._create_contract(emp, wage=SALARIO, date_start=date(2018, 1, 1))
            c1.write({"date_end": date(2019, 12, 31), "state": "close"})
        velha = self._alocacao(emp, date(2019, 1, 1), date(2019, 12, 31))
        self._create_contract(emp, wage=SALARIO, date_start=date(2023, 1, 15))
        nova = self._alocacao(emp, date(2023, 1, 15), date(2024, 1, 14))
        return emp, velha, nova

    def _confere_debito(self, com_contrato_anterior):
        emp, velha, nova = self._readmissao(com_contrato_anterior)
        leave = self._ausencia(emp, date(2024, 3, 4), date(2024, 3, 13))
        self.assertEqual(leave._l10n_br_periodo_da_ausencia(), nova)
        self.assertFalse(leave.l10n_br_aviso_dobro)
        self.assertNotEqual(leave._l10n_br_periodo_da_ausencia(), velha)

    def test_readmissao_ausencia_debita_a_alocacao_do_vinculo_novo(self):
        self._confere_debito(com_contrato_anterior=False)

    def test_readmissao_com_contrato_anterior_ausencia_nao_debita_a_velha(self):
        self._confere_debito(com_contrato_anterior=True)

    def test_troca_de_contrato_ausencia_debita_a_alocacao_do_primeiro(self):
        emp = self._create_employee()
        c1 = self._create_contract(emp, wage=SALARIO, date_start=date(2023, 1, 15))
        c1.write({"date_end": date(2023, 4, 14), "state": "close"})
        self._create_contract(emp, wage=SALARIO, date_start=date(2023, 4, 15))
        a = self._alocacao(emp, date(2023, 1, 15), date(2024, 1, 14))
        leave = self._ausencia(emp, date(2024, 3, 4), date(2024, 3, 13))
        self.assertEqual(leave._l10n_br_periodo_da_ausencia(), a)
