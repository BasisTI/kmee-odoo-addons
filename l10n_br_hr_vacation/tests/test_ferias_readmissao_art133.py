# Copyright 2026 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""TG-165: readmissão, alocação além da projeção e período perdido (art. 133).

Contrato em 15/01/2023, salário 3.000,00, dispensa em 31/12/2025 com aviso
indenizado de 33 dias (projeção até 02/02/2026).
"""
from datetime import date

from odoo.exceptions import UserError
from odoo.tests import tagged

from .common import VacationCommon

SALARIO = 3000.0
DESLIGAMENTO = date(2025, 12, 31)


@tagged("post_install", "-at_install")
class TestFeriasReadmissaoArt133(VacationCommon):
    exigir_alocacao_periodo = True

    def _contrato(self):
        emp = self._create_employee()
        contract = self._create_contract(
            emp, wage=SALARIO, date_start=date(2023, 1, 15)
        )
        return emp, contract

    def _alocacao(self, emp, periodo, **extra):
        alloc = self.env["hr.leave.allocation"].create(
            dict(
                {
                    "employee_id": emp.id,
                    "holiday_status_id": self.leave_type_ferias.id,
                    "date_from": periodo[0],
                    "date_to": periodo[1],
                },
                **extra,
            )
        )
        alloc.action_validate()
        return alloc

    def _rescisao(self, emp, contract):
        contract.date_end = DESLIGAMENTO
        slip = self.env["hr.payslip"].create(
            {
                "name": "TG-165",
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

    def _recusa(self, emp, contract, regex):
        with self.assertRaisesRegex(UserError, regex), self.env.cr.savepoint():
            self._rescisao(emp, contract)

    # ---- 1. readmissão -------------------------------------------------------

    def _vinculo_anterior(self, emp):
        self._alocacao(emp, (date(2018, 1, 1), date(2018, 12, 31)))
        self._alocacao(emp, (date(2019, 1, 1), date(2019, 12, 31)))

    def test_readmissao_indicacao_segue_o_contrato_atual(self):
        emp, contract = self._contrato()
        self._vinculo_anterior(emp)
        self._recusa(emp, contract, "15/01/2025 a 14/01/2026")

    def test_readmissao_nao_paga_vencidas_do_vinculo_anterior(self):
        emp, contract = self._contrato()
        self._vinculo_anterior(emp)
        self._alocacao(emp, (date(2025, 1, 15), date(2026, 1, 14)))
        slip = self._rescisao(emp, contract)
        self.assertEqual(len(slip._l10n_br_ferias_vencidas_dados()), 1)
        self.assertEqual(self._get_line_total(slip, "FERIAS_VENCIDAS"), 3000.0)

    def test_readmissao_sobreposicao_so_do_vinculo_atual(self):
        """Duplicata no vínculo anterior não trava a rescisão do atual."""
        emp, contract = self._contrato()
        self._alocacao(emp, (date(2018, 1, 1), date(2018, 12, 31)))
        self._alocacao(emp, (date(2018, 6, 1), date(2019, 5, 31)))
        self._alocacao(emp, (date(2025, 1, 15), date(2026, 1, 14)))
        slip = self._rescisao(emp, contract)
        self.assertEqual(self._get_line_total(slip, "FERIAS_VENCIDAS"), 3000.0)

    # ---- 2. alocação que termina depois da referência ------------------------

    def _anos_civis(self, emp):
        self._alocacao(emp, (date(2023, 1, 15), date(2023, 12, 31)))
        self._alocacao(emp, (date(2024, 1, 1), date(2024, 12, 31)))

    def test_alocacao_alem_da_projecao_indicacao_termina_na_vespera(self):
        emp, contract = self._contrato()
        self._anos_civis(emp)
        seguinte = self._alocacao(emp, (date(2025, 3, 15), date(2026, 3, 14)))
        with self.assertRaises(UserError) as cm, self.env.cr.savepoint():
            self._rescisao(emp, contract)
        self.assertIn("01/01/2025 a 14/03/2025", cm.exception.args[0])
        # a indicação é criável: criada, a rescisão calcula
        self._alocacao(emp, (date(2025, 1, 1), date(2025, 3, 14)))
        slip = self._rescisao(emp, contract)
        self.assertTrue(slip.line_ids)
        self.assertEqual(seguinte.state, "validate")

    def test_alocacao_alem_da_projecao_sem_janela_pede_ajuste_dela(self):
        emp, contract = self._contrato()
        self._alocacao(emp, (date(2023, 1, 15), date(2024, 1, 14)))
        self._alocacao(emp, (date(2024, 1, 15), date(2025, 1, 14)))
        ocupa = self._alocacao(emp, (date(2025, 1, 20), date(2026, 3, 31)))
        with self.assertRaises(UserError) as cm, self.env.cr.savepoint():
            self._rescisao(emp, contract)
        self.assertIn("já ocupa o período", cm.exception.args[0])
        self.assertIn("id %s" % ocupa.id, cm.exception.args[0])

    def test_sobreposicao_com_alocacao_que_termina_depois_recusa(self):
        emp, contract = self._contrato()
        self._alocacao(emp, (date(2025, 1, 15), date(2026, 1, 14)))
        b = self._alocacao(emp, (date(2025, 6, 1), date(2026, 5, 31)))
        self._recusa(emp, contract, "mesmo período aquisitivo")
        b.action_refuse()
        self._rescisao(emp, contract)

    # ---- 3. período perdido (art. 133) ---------------------------------------

    def _alocacoes_com_periodo_perdido(self, emp, marca=True):
        self._alocacao(emp, (date(2023, 1, 15), date(2024, 1, 14)))
        self._alocacao(emp, (date(2024, 1, 15), date(2025, 1, 14)))
        return self._alocacao(
            emp,
            (date(2025, 1, 15), date(2026, 1, 14)),
            l10n_br_faltas_periodo_aquisitivo=33,
            l10n_br_periodo_perdido=marca,
        )

    def test_periodo_perdido_e_aceito_e_nao_gera_pagamento(self):
        emp, contract = self._contrato()
        self._alocacoes_com_periodo_perdido(emp)
        slip = self._rescisao(emp, contract)
        self.assertEqual(len(slip._l10n_br_ferias_vencidas_dados()), 2)
        # 2023 vencido em dobro (6.000,00) + 2024 (3.000,00); o perdido, nada
        self.assertEqual(self._get_line_total(slip, "FERIAS_VENCIDAS"), 9000.0)
        self.assertEqual(
            self._get_line_total(slip, "ADICIONAL_FERIAS_VENCIDAS"), 3000.0
        )

    def test_periodo_perdido_sem_a_marca_continua_pagando_o_dia(self):
        """O contorno da TG-147 (sem a marca): 1 dia mais o terço."""
        emp, contract = self._contrato()
        self._alocacoes_com_periodo_perdido(emp, marca=False)
        slip = self._rescisao(emp, contract)
        self.assertEqual(len(slip._l10n_br_ferias_vencidas_dados()), 3)
        self.assertGreater(self._get_line_total(slip, "FERIAS_VENCIDAS"), 9000.0)

    def test_periodo_perdido_nao_tem_saldo_para_ausencia(self):
        emp, _contract = self._contrato()
        perdida = self._alocacoes_com_periodo_perdido(emp)
        saldo = self.env["hr.leave.allocation"]._l10n_br_saldo_corridos(perdida)
        self.assertEqual(saldo[perdida], 0)

    def test_marca_de_periodo_perdido_e_travada_com_rescisao_confirmada(self):
        emp, contract = self._contrato()
        perdida = self._alocacoes_com_periodo_perdido(emp)
        slip = self._rescisao(emp, contract)
        slip.action_payslip_done()
        with self.assertRaisesRegex(UserError, "rescisão confirmada"):
            with self.env.cr.savepoint():
                perdida.write({"l10n_br_periodo_perdido": False})
        self.assertTrue(perdida.l10n_br_periodo_perdido)

    def test_marca_de_periodo_perdido_com_rescisao_aberta_recalcula(self):
        emp, contract = self._contrato()
        perdida = self._alocacoes_com_periodo_perdido(emp, marca=False)
        slip = self._rescisao(emp, contract)
        self.assertEqual(len(slip._l10n_br_ferias_vencidas_dados()), 3)
        perdida.write({"l10n_br_periodo_perdido": True})
        slip.compute_sheet()
        self.assertEqual(len(slip._l10n_br_ferias_vencidas_dados()), 2)
