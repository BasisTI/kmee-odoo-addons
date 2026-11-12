# Copyright 2026 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""TG-88: periculosidade e insalubridade na base de férias, 13º e rescisão.

Adicional contratual fixo não varia mês a mês: entra pelo valor CHEIO do
contrato (30% do salário; 10/20/40% do salário mínimo), não por média
(CLT art. 142, § 5º; Súmulas 132 e 139 do TST).
"""
from datetime import date

from odoo.tests import tagged

from .common import VacationCommon

SALARIO = 3000.0
PERICULOSIDADE = 900.0  # 30% de 3.000
BASE = SALARIO + PERICULOSIDADE


@tagged("post_install", "-at_install")
class TestAdicionaisFixosBases(VacationCommon):
    def _contrato(self, **flags):
        emp = self._create_employee()
        contract = self._create_contract(emp, wage=SALARIO, date_start=date(2024, 1, 2))
        contract.write(flags)
        return emp, contract

    def _slip(self, emp, contract, struct, inicio, fim, **extra):
        slip = self.env["hr.payslip"].create(
            {
                "name": "TG-88",
                "employee_id": emp.id,
                "contract_id": contract.id,
                "struct_id": struct.id,
                "date_from": inicio,
                "date_to": fim,
                "company_id": self.env.company.id,
                **extra,
            }
        )
        slip.compute_sheet()
        return slip

    def _recibo_ferias(self, emp, contract, dias_gozo, dias_abono=0):
        alloc = self.env["hr.leave.allocation"].create(
            {
                "employee_id": emp.id,
                "holiday_status_id": self.leave_type_ferias.id,
                "date_from": date(2025, 1, 2),
                "date_to": date(2026, 1, 1),
            }
        )
        alloc.action_validate()
        return self._slip(
            emp,
            contract,
            self.structure_ferias,
            date(2026, 11, 16),
            date(2026, 11, 25),
            l10n_br_ferias_allocation_id=alloc.id,
            l10n_br_dias_periodo_gozado=dias_gozo,
            l10n_br_dias_abono=dias_abono,
        )

    def _salario_minimo(self, data):
        return self.env["l10n_br.hr.payroll.inss.faixa"]._salario_minimo(data)

    # --- férias ---------------------------------------------------------

    def test_ferias_incluem_periculosidade(self):
        emp, contract = self._contrato(l10n_br_periculosidade=True)
        recibo = self._recibo_ferias(emp, contract, 10)
        ferias = round(BASE * 10 / 30, 2)
        self.assertAlmostEqualMoney(self._get_line_total(recibo, "FERIAS"), ferias)
        self.assertAlmostEqualMoney(
            self._get_line_total(recibo, "ADICIONAL_FERIAS"), round(ferias / 3, 2)
        )

    def test_ferias_sem_adicional_nao_mudam(self):
        emp, contract = self._contrato()
        recibo = self._recibo_ferias(emp, contract, 10)
        self.assertAlmostEqualMoney(self._get_line_total(recibo, "FERIAS"), 1000.0)

    def test_ferias_incluem_insalubridade(self):
        emp, contract = self._contrato(
            l10n_br_insalubridade=True, l10n_br_grau_insalubridade="medio"
        )
        recibo = self._recibo_ferias(emp, contract, 10)
        adicional = round(self._salario_minimo(date(2026, 11, 25)) * 0.20, 2)
        self.assertAlmostEqualMoney(
            self._get_line_total(recibo, "FERIAS"),
            round((SALARIO + adicional) * 10 / 30, 2),
        )

    def test_abono_pecuniario_inclui_periculosidade(self):
        emp, contract = self._contrato(l10n_br_periculosidade=True)
        recibo = self._recibo_ferias(emp, contract, 20, dias_abono=10)
        self.assertAlmostEqualMoney(
            self._get_line_total(recibo, "ABONO_PECUNIARIO"), round(BASE / 30 * 10, 2)
        )

    def test_ferias_compoem_gross_e_fgts_com_periculosidade(self):
        emp, contract = self._contrato(l10n_br_periculosidade=True)
        recibo = self._recibo_ferias(emp, contract, 10)
        ferias = round(BASE * 10 / 30, 2)
        gross = self._get_line_total(recibo, "GROSS")
        self.assertAlmostEqualMoney(gross, round(ferias + round(ferias / 3, 2), 2))
        self.assertAlmostEqualMoney(
            self._get_line_total(recibo, "FGTS"), round(gross * 0.08, 2)
        )

    # --- 13º ------------------------------------------------------------

    def test_decimo_terceiro_inclui_periculosidade(self):
        emp, contract = self._contrato(l10n_br_periculosidade=True)
        decimo = self._slip(
            emp, contract, self.structure_13, date(2025, 12, 1), date(2025, 12, 31)
        )
        avos = decimo.l10n_br_avos_13
        self.assertGreater(avos, 0)
        self.assertAlmostEqualMoney(
            self._get_line_total(decimo, "DECIMO_TERCEIRO_BRUTO"),
            round(BASE * avos / 12, 2),
        )

    def test_adiantamento_13_inclui_periculosidade(self):
        emp, contract = self._contrato(l10n_br_periculosidade=True)
        slip = self._slip(
            emp,
            contract,
            self.structure_13_primeira,
            date(2025, 11, 1),
            date(2025, 11, 30),
        )
        # Projeção a 31/12: contrato de 2024, ano cheio = 12 avos, metade de 3.900.
        self.assertAlmostEqualMoney(
            self._get_line_total(slip, "ADIANTAMENTO_13"), BASE * 0.5
        )

    # --- rescisão -------------------------------------------------------

    def _rescisao(self, emp, contract, **extra):
        return self._slip(
            emp,
            contract,
            self.structure_rescisao,
            date(2025, 9, 1),
            date(2025, 9, 30),
            l10n_br_tipo_rescisao="sem_justa_causa",
            **extra,
        )

    def test_rescisao_inclui_periculosidade_no_13_e_nas_ferias(self):
        emp, contract = self._contrato(l10n_br_periculosidade=True)
        rescisao = self._rescisao(emp, contract)
        avos_13 = rescisao.l10n_br_avos_13
        avos_ferias = rescisao.l10n_br_avos_ferias
        self.assertGreater(avos_13, 0)
        self.assertAlmostEqualMoney(
            self._get_line_total(rescisao, "DECIMO_RESCISAO"),
            round(BASE * avos_13 / 12, 2),
        )
        if avos_ferias:
            self.assertAlmostEqualMoney(
                self._get_line_total(rescisao, "FERIAS_INDENIZADAS"),
                round(BASE * avos_ferias / 12, 2),
            )

    def test_rescisao_inclui_periculosidade_no_aviso_indenizado(self):
        emp, contract = self._contrato(l10n_br_periculosidade=True)
        rescisao = self._rescisao(emp, contract, l10n_br_aviso_previo="indenizado")
        dias = rescisao._l10n_br_dias_aviso_previo()
        self.assertGreater(dias, 0)
        self.assertAlmostEqualMoney(
            self._get_line_total(rescisao, "AVISO_PREVIO_INDENIZADO"),
            round(BASE / 30 * dias, 2),
        )

    def test_saldo_de_salario_inclui_periculosidade_e_alimenta_as_bases(self):
        emp, contract = self._contrato(l10n_br_periculosidade=True)
        rescisao = self._rescisao(emp, contract)
        saldo = self._get_line_total(rescisao, "SALDO_SALARIO")
        self.assertAlmostEqualMoney(saldo, BASE)
        # Bases do saldo: FGTS 8% e INSS sobre o saldo com o adicional.
        self.assertAlmostEqualMoney(
            self._get_line_total(rescisao, "FGTS"), round(saldo * 0.08, 2)
        )
        sem = self._rescisao(*self._contrato())
        self.assertGreater(
            self._get_line_total(rescisao, "INSS"), self._get_line_total(sem, "INSS")
        )

    def test_saldo_nao_paga_de_novo_o_que_o_mensal_ja_pagou(self):
        emp, contract = self._contrato(l10n_br_periculosidade=True)
        self._create_payslip(emp, contract, date(2025, 9, 1), date(2025, 9, 30))
        rescisao = self._rescisao(emp, contract)
        self.assertAlmostEqualMoney(self._get_line_total(rescisao, "SALDO_SALARIO"), 0)
