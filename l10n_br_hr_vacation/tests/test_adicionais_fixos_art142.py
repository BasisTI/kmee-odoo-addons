# Copyright 2026 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""TG-133: média dos adicionais pela letra do CLT art. 142 § 6º.

Cinco pontos (decisão TG-133#P1), cada um conferido em férias, 13º e rescisão:

1. janela: período aquisitivo nas férias; ano civil no 13º;
2. média quando o adicional não foi uniforme, mesmo para quem o tem hoje;
3. mês sem dias de salário fica fora do divisor;
4. aviso prévio indenizado: remuneração do momento, sem média;
5. média atualizada pelos reajustes salariais.

Salário 3.000 e periculosidade de 900 (30%). Contrato admitido em 01/01/2024:
o período aquisitivo de 2025, o ano civil de 2025 e as férias proporcionais da
rescisão em 31/12/2025 cobrem os mesmos meses (janeiro a novembro de 2025, os
mensais de competência anterior à do holerite).
"""
import calendar
from datetime import date

from odoo.tests import tagged

from .common import VacationCommon

SALARIO = 3000.0


@tagged("post_install", "-at_install")
class TestAdicionaisFixosArt142(VacationCommon):
    def _contrato(self, wage=SALARIO, **flags):
        emp = self._create_employee()
        contract = self._create_contract(emp, wage=wage, date_start=date(2024, 1, 1))
        contract.write(flags)
        return emp, contract

    def _holerite(self, emp, contract, struct, de, ate, **extra):
        slip = self.env["hr.payslip"].create(
            {
                "name": "TG-133",
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

    def _mensal(self, emp, contract, ano, mes):
        fim = date(ano, mes, calendar.monthrange(ano, mes)[1])
        slip = self._holerite(emp, contract, self.structure_clt, date(ano, mes, 1), fim)
        slip.action_payslip_done()
        return slip

    def _alocacao(self, emp, inicio, fim):
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

    def _historico(self, emp, contract, meses=None, com=None, wage=None):
        """Mensais confirmados de 2025; ``com(mes)`` diz se há periculosidade.

        ``wage(mes)`` troca o salário do contrato a cada mês, se informado.
        """
        for mes in meses or range(1, 12):
            if com is not None:
                contract.l10n_br_periculosidade = com(mes)
            if wage is not None:
                contract.wage = wage(mes)
            self._mensal(emp, contract, 2025, mes)

    # --- as três verbas sobre o mesmo histórico ----------------------------

    def _ferias(self, emp, contract):
        alloc = self._alocacao(emp, date(2025, 1, 1), date(2025, 12, 31))
        return self._holerite(
            emp,
            contract,
            self.structure_ferias,
            date(2026, 1, 5),
            date(2026, 1, 14),
            l10n_br_ferias_allocation_id=alloc.id,
            l10n_br_dias_periodo_gozado=10,
        )

    def _decimo(self, emp, contract):
        return self._holerite(
            emp, contract, self.structure_13, date(2025, 12, 1), date(2025, 12, 31)
        )

    def _rescisao(self, emp, contract, **extra):
        contract.date_end = date(2025, 12, 31)
        return self._holerite(
            emp,
            contract,
            self.structure_rescisao,
            date(2025, 12, 1),
            date(2025, 12, 31),
            l10n_br_tipo_rescisao=extra.pop("tipo", "pedido_demissao"),
            l10n_br_aviso_previo=extra.pop("aviso", "nao_aplicavel"),
            **extra,
        )

    def _confere(self, emp, contract, adicional, salario=SALARIO):
        """Férias, 13º e rescisão levam o mesmo ``adicional`` na base."""
        base = salario + adicional
        ferias = self._ferias(emp, contract)
        self.assertAlmostEqualMoney(
            self._get_line_total(ferias, "FERIAS"), round(base * 10 / 30, 2)
        )
        decimo = self._decimo(emp, contract)
        self.assertEqual(decimo.l10n_br_avos_13, 12)
        self.assertAlmostEqualMoney(
            self._get_line_total(decimo, "DECIMO_TERCEIRO_BRUTO"), round(base, 2)
        )
        rescisao = self._rescisao(emp, contract)
        self.assertEqual(rescisao.l10n_br_avos_ferias, 12)
        self.assertAlmostEqualMoney(
            self._get_line_total(rescisao, "FERIAS_INDENIZADAS"), round(base, 2)
        )
        self.assertAlmostEqualMoney(
            self._get_line_total(rescisao, "DECIMO_RESCISAO"), round(base, 2)
        )

    # --- 1. janela ---------------------------------------------------------

    def test_ponto1_periodo_todo_com_adicional_paga_o_adicional_cheio(self):
        # Teve o adicional o período aquisitivo inteiro e o perdeu depois: a
        # média do período é o valor cheio, não a dos últimos 12 meses.
        emp, contract = self._contrato(l10n_br_periculosidade=True)
        self._historico(emp, contract, com=lambda mes: True)
        contract.l10n_br_periculosidade = False
        self._confere(emp, contract, 900.0)

    def test_ponto1_ferias_meses_depois_do_periodo_aquisitivo(self):
        # Férias em 11/2026: a janela dos 12 meses antes (11/2025 a 10/2026)
        # pegaria só dois meses com adicional; o período aquisitivo (2025) o
        # teve inteiro.
        emp, contract = self._contrato(l10n_br_periculosidade=True)
        self._historico(emp, contract, meses=range(1, 13), com=lambda mes: True)
        contract.l10n_br_periculosidade = False
        for mes in range(7, 11):
            self._mensal(emp, contract, 2026, mes)
        alloc = self._alocacao(emp, date(2025, 1, 1), date(2025, 12, 31))
        recibo = self._holerite(
            emp,
            contract,
            self.structure_ferias,
            date(2026, 11, 16),
            date(2026, 11, 25),
            l10n_br_ferias_allocation_id=alloc.id,
            l10n_br_dias_periodo_gozado=10,
        )
        self.assertAlmostEqualMoney(
            self._get_line_total(recibo, "FERIAS"), round((3000 + 900) * 10 / 30, 2)
        )

    # --- 2. quem tem o adicional hoje, mas não no período todo -------------

    def test_ponto2_tem_hoje_mas_nao_no_periodo_todo_leva_a_media(self):
        emp, contract = self._contrato()
        self._historico(emp, contract, com=lambda mes: mes >= 7)
        self.assertTrue(contract.l10n_br_periculosidade)
        # 5 meses de 900 entre 11 mensais; o cheio de hoje (900) não vale.
        self._confere(emp, contract, round(4500 / 11, 2))

    def test_adicional_uniforme_e_igual_ao_vigente_nao_muda(self):
        emp, contract = self._contrato(l10n_br_periculosidade=True)
        self._historico(emp, contract, com=lambda mes: True)
        self._confere(emp, contract, 900.0)

    # --- 3. mês sem dias de salário fora do divisor ------------------------

    def test_ponto3_mes_de_ferias_gozadas_nao_baixa_a_media(self):
        emp, contract = self._contrato(l10n_br_periculosidade=True)
        self._historico(emp, contract, meses=range(1, 6), com=lambda mes: True)
        # Junho inteiro de férias gozadas: o mensal não tem dias de salário.
        alloc = self._alocacao(emp, date(2024, 1, 1), date(2024, 12, 31))
        recibo = self._holerite(
            emp,
            contract,
            self.structure_ferias,
            date(2025, 6, 1),
            date(2025, 6, 30),
            l10n_br_ferias_allocation_id=alloc.id,
            l10n_br_dias_periodo_gozado=30,
        )
        recibo.action_payslip_done()
        junho = self._mensal(emp, contract, 2025, 6)
        self.assertAlmostEqualMoney(
            self._get_line_total(junho, "ADICIONAL_PERICULOSIDADE"), 0.0
        )
        self._historico(emp, contract, meses=range(7, 12), com=lambda mes: True)
        contract.l10n_br_periculosidade = False
        # 10 meses com dias de salário, todos de 900: média 900 (e não 818,18,
        # com junho como zero).
        self._confere(emp, contract, 900.0)

    # --- 4. aviso prévio indenizado ---------------------------------------

    def test_ponto4_aviso_indenizado_usa_a_remuneracao_do_momento(self):
        emp, contract = self._contrato(l10n_br_periculosidade=True)
        self._historico(emp, contract, com=lambda mes: mes <= 9)
        self.assertFalse(contract.l10n_br_periculosidade)
        rescisao = self._rescisao(
            emp, contract, tipo="sem_justa_causa", aviso="indenizado"
        )
        dias = rescisao._l10n_br_dias_aviso_previo()
        self.assertGreater(dias, 0)
        # Perdeu o adicional há dois meses: o aviso paga o salário, sem média.
        self.assertAlmostEqualMoney(
            self._get_line_total(rescisao, "AVISO_PREVIO_INDENIZADO"),
            round(SALARIO / 30 * dias, 2),
        )

    def test_ponto4_aviso_indenizado_de_quem_tem_o_adicional_hoje(self):
        emp, contract = self._contrato()
        self._historico(emp, contract, com=lambda mes: mes >= 7)
        rescisao = self._rescisao(
            emp, contract, tipo="sem_justa_causa", aviso="indenizado"
        )
        dias = rescisao._l10n_br_dias_aviso_previo()
        self.assertAlmostEqualMoney(
            self._get_line_total(rescisao, "AVISO_PREVIO_INDENIZADO"),
            round((SALARIO + 900) / 30 * dias, 2),
        )

    # --- 5. reajustes --------------------------------------------------------

    def test_ponto5_media_atualizada_pelo_reajuste_do_salario(self):
        emp, contract = self._contrato()
        self._historico(
            emp,
            contract,
            com=lambda mes: mes <= 6,
            wage=lambda mes: 3000.0 if mes <= 6 else 3600.0,
        )
        self.assertFalse(contract.l10n_br_periculosidade)
        self.assertEqual(contract.wage, 3600.0)
        # 6 meses de 900 a salário de 3.000, atualizados a 3.600 (x 1,2), em
        # 11 meses: 6.480 / 11. A média nominal (4.500 / 11) pagaria menos.
        self._confere(emp, contract, round(6480 / 11, 2), salario=3600.0)
