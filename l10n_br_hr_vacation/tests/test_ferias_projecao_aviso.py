# Copyright 2026 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""TG-147: período de férias que se completa na projeção do aviso indenizado.

Súmula 371 TST e CLT art. 487 § 1º: o aviso indenizado projeta o contrato. Se a
projeção passa do aniversário de admissão, o período aquisitivo que se completa
nela é devido inteiro (``FERIAS_VENCIDAS`` + terço) e os avos proporcionais
contam do aniversário. A fonte do período é a alocação de Férias do
``hr_holidays``.

Admissão em 15/01/2024, salário 3.000,00, dispensa sem justa causa com aviso
indenizado de 33 dias; alocação de 15/01/2025 a 14/01/2026.
"""
from datetime import date, timedelta

from odoo.tests import tagged

from .common import VacationCommon

SALARIO = 3000.0
AQ_INI, AQ_FIM = date(2025, 1, 15), date(2026, 1, 14)


@tagged("post_install", "-at_install")
class TestFeriasProjecaoAviso(VacationCommon):
    def _contrato(self, wage=SALARIO):
        emp = self._create_employee()
        contract = self._create_contract(emp, wage=wage, date_start=date(2024, 1, 15))
        return emp, contract

    def _alocacao(self, emp, inicio=AQ_INI, fim=AQ_FIM):
        alloc = self.env["hr.leave.allocation"].create(
            {
                "employee_id": emp.id,
                "holiday_status_id": self.leave_type_ferias.id,
                "date_from": inicio,
                "date_to": fim,
            }
        )
        alloc.action_validate()
        return alloc

    def _holerite(self, emp, contract, struct, de, ate, **extra):
        slip = self.env["hr.payslip"].create(
            {
                "name": "TG-147",
                "employee_id": emp.id,
                "contract_id": contract.id,
                "struct_id": struct.id,
                "date_from": de,
                "date_to": ate,
                "company_id": self.env.company.id,
                **extra,
            }
        )
        slip.compute_sheet()
        return slip

    def _rescisao(self, emp, contract, desligamento, aviso="indenizado", **extra):
        contract.date_end = desligamento
        return self._holerite(
            emp,
            contract,
            self.structure_rescisao,
            desligamento.replace(day=1),
            desligamento,
            l10n_br_tipo_rescisao=extra.pop("tipo", "sem_justa_causa"),
            l10n_br_aviso_previo=aviso,
            **extra,
        )

    def _caso(self, projecao, **kwargs):
        """Rescisão cuja projeção (33 dias de aviso) termina em ``projecao``."""
        emp, contract = self._contrato()
        self._alocacao(emp)
        return self._rescisao(emp, contract, projecao - timedelta(days=33), **kwargs)

    def _vencidas(self, slip):
        return (
            self._get_line_total(slip, "FERIAS_VENCIDAS"),
            self._get_line_total(slip, "ADICIONAL_FERIAS_VENCIDAS"),
        )

    # ---- o caso da story ---------------------------------------------------

    def test_caso_da_story_33_dias_cruzando_o_aniversario(self):
        """Dispensa em 31/12/2025, aviso até 02/02/2026: 12/12 + 1/12 novo."""
        emp, contract = self._contrato()
        self._alocacao(emp)
        slip = self._rescisao(emp, contract, date(2025, 12, 31))
        self.assertEqual(slip._l10n_br_data_projetada_rescisao(), date(2026, 2, 2))
        self.assertEqual(slip.l10n_br_avos_ferias, 1)
        self.assertAlmostEqualMoney(
            self._get_line_total(slip, "FERIAS_INDENIZADAS"), 250
        )
        self.assertAlmostEqualMoney(
            self._get_line_total(slip, "ADICIONAL_FERIAS_INDENIZADAS"), 83.33
        )
        self.assertEqual(self._vencidas(slip), (3000.0, 1000.0))
        dados = slip._l10n_br_ferias_vencidas_dados()
        self.assertEqual(len(dados), 1)
        self.assertFalse(dados[0]["dobro"])

    # ---- projeção cruzando o aniversário por 1, 3 e 30 dias ---------------

    def test_cruza_por_1_dia(self):
        slip = self._caso(date(2026, 1, 15))
        # O novo período começa no aniversário: 1 dia não gera avo.
        self.assertEqual(slip.l10n_br_avos_ferias, 0)
        self.assertEqual(self._vencidas(slip), (3000.0, 1000.0))

    def test_cruza_por_3_dias(self):
        slip = self._caso(date(2026, 1, 17))
        self.assertEqual(slip.l10n_br_avos_ferias, 0)
        self.assertEqual(self._vencidas(slip), (3000.0, 1000.0))

    def test_cruza_por_30_dias(self):
        slip = self._caso(date(2026, 2, 13))
        self.assertEqual(slip.l10n_br_avos_ferias, 1)
        self.assertEqual(self._vencidas(slip), (3000.0, 1000.0))

    def test_projecao_termina_no_ultimo_dia_do_periodo(self):
        """Projeção até 14/01/2026: o período completa nela."""
        slip = self._caso(date(2026, 1, 14))
        self.assertEqual(self._vencidas(slip), (3000.0, 1000.0))

    def test_sem_cruzar_o_aniversario(self):
        """Projeção até 13/01/2026: o período continua em curso (proporcional)."""
        slip = self._caso(date(2026, 1, 13))
        self.assertEqual(slip.l10n_br_avos_ferias, 12)
        self.assertEqual(self._vencidas(slip), (0.0, 0.0))
        self.assertAlmostEqualMoney(
            self._get_line_total(slip, "FERIAS_INDENIZADAS"), 3000
        )

    # ---- sem projeção -------------------------------------------------------

    def test_aviso_trabalhado_nao_projeta(self):
        emp, contract = self._contrato()
        self._alocacao(emp)
        slip = self._rescisao(emp, contract, date(2025, 12, 31), aviso="trabalhado")
        self.assertEqual(self._vencidas(slip), (0.0, 0.0))
        self.assertEqual(slip.l10n_br_avos_ferias, 12)

    def test_sem_alocacao_nao_ha_periodo_vencido(self):
        emp, contract = self._contrato()
        slip = self._rescisao(emp, contract, date(2025, 12, 31))
        self.assertEqual(self._vencidas(slip), (0.0, 0.0))

    def test_periodo_ja_completo_no_desligamento_segue_igual(self):
        """Período fechado antes da dispensa: vencido como sempre, e o período
        da projeção entra junto se houver alocação dele."""
        emp, contract = self._contrato()
        self._alocacao(emp, date(2024, 1, 15), date(2025, 1, 14))
        self._alocacao(emp)
        slip = self._rescisao(emp, contract, date(2025, 12, 31))
        self.assertEqual(len(slip._l10n_br_ferias_vencidas_dados()), 2)
        self.assertEqual(self._vencidas(slip), (6000.0, 2000.0))

    # ---- adicionais (TG-133) -----------------------------------------------

    def test_periculosidade_vigente_entra_no_periodo_da_projecao(self):
        emp, contract = self._contrato()
        contract.l10n_br_periculosidade = True
        self._alocacao(emp)
        slip = self._rescisao(emp, contract, date(2025, 12, 31))
        # Sem mensais confirmados no período, vale o adicional vigente (30%).
        self.assertEqual(self._vencidas(slip), (3900.0, 1300.0))

    def test_periculosidade_nao_uniforme_leva_a_media_do_periodo(self):
        emp, contract = self._contrato()
        self._alocacao(emp)
        for mes in range(2, 12):
            contract.l10n_br_periculosidade = mes >= 7
            mensal = self._holerite(
                emp,
                contract,
                self.structure_clt,
                date(2025, mes, 1),
                date(2025, mes, 28 if mes == 2 else 30),
            )
            mensal.action_payslip_done()
        contract.l10n_br_periculosidade = True
        slip = self._rescisao(emp, contract, date(2025, 12, 31))
        # 5 dos 10 meses com 900: média de 450, não os 900 vigentes.
        vencidas, terco = self._vencidas(slip)
        self.assertAlmostEqualMoney(vencidas, 3450.0)
        self.assertAlmostEqualMoney(terco, 1150.0)

    # ---- saldo já pago ------------------------------------------------------

    def test_dias_ja_pagos_do_periodo_anterior_abatem_o_saldo(self):
        """Férias de 10 dias gozadas do 1º período: restam 20 dele, mais os 30
        do período que fecha na projeção."""
        emp, contract = self._contrato()
        anterior = self._alocacao(emp, date(2024, 1, 15), date(2025, 1, 14))
        self._alocacao(emp)
        ferias = self._holerite(
            emp,
            contract,
            self.structure_ferias,
            date(2025, 3, 3),
            date(2025, 3, 12),
            l10n_br_ferias_allocation_id=anterior.id,
            l10n_br_dias_periodo_gozado=10,
        )
        ferias.action_payslip_done()
        slip = self._rescisao(emp, contract, date(2025, 12, 31))
        dados = slip._l10n_br_ferias_vencidas_dados()
        self.assertEqual(sorted(d["dias"] for d in dados), [20, 30])
        self.assertAlmostEqualMoney(self._vencidas(slip)[0], 5000.0)
