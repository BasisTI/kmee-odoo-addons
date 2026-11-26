# Copyright 2026 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""TG-168: férias, 13º e rescisão do horista pela média das horas.

CLT art. 142, § 1º; Lei 4.090/62 e Decreto 57.155/65, art. 2º: o salário de
referência do horista é a média das horas pagas no período vezes o valor da hora
vigente (mais o repouso). O mensalista não muda.
"""

from datetime import date

from dateutil.relativedelta import relativedelta

from odoo.exceptions import UserError
from odoo.tests import tagged

from odoo.addons.l10n_br_hr_payroll.models.salary_rules_br import round_money

from .common import VacationCommon

VALOR_HORA = 20.0


@tagged("post_install", "-at_install")
class TestHoristaFerias13Rescisao(VacationCommon):
    def _horista(self, date_start=None, calendario=None):
        date_start = date_start or date(2024, 1, 1)
        emp = self._create_employee("Horista TG-168")
        contract = self._create_contract(emp, wage=3500.0, date_start=date_start)
        valores = {
            "salary_unit": self._unidade_salario("1").id,
            "l10n_br_valor_hora": VALOR_HORA,
        }
        if calendario:
            valores["resource_calendar_id"] = calendario.id
        contract.write(valores)
        return emp, contract

    def _mensal(self, emp, contract, ano, mes, horas):
        slip = self.env["hr.payslip"].create(
            {
                "name": f"Mensal {mes}/{ano}",
                "employee_id": emp.id,
                "contract_id": contract.id,
                "struct_id": self.structure_clt.id,
                "date_from": date(ano, mes, 1),
                "date_to": date(ano, mes, 1) + relativedelta(day=31),
                "l10n_br_horas_pagas": horas,
                "company_id": self.env.company.id,
            }
        )
        slip.compute_sheet()
        slip.action_payslip_done()
        return slip

    @staticmethod
    def _media(remuneracoes):
        return round_money(sum(remuneracoes) / len(remuneracoes))

    def _historico_2024(self, emp, contract, ate_mes=12):
        """Jan-jun com 100 h e jul-dez com 160 h; devolve a média esperada."""
        remuneracoes = []
        for mes in range(1, 13):
            slip = self._mensal(emp, contract, 2024, mes, 100.0 if mes < 7 else 160.0)
            remuneracoes.append(
                self._get_line_total(slip, "SALARIO_BASE")
                + self._get_line_total(slip, "DSR_HORISTA")
            )
        self.media_ate_novembro = self._media(remuneracoes[:11])
        return self._media(remuneracoes[:ate_mes])

    def _slip(self, emp, contract, estrutura, inicio, fim, **extra):
        slip = self.env["hr.payslip"].create(
            dict(
                {
                    "name": "Verba horista",
                    "employee_id": emp.id,
                    "contract_id": contract.id,
                    "struct_id": estrutura.id,
                    "date_from": inicio,
                    "date_to": fim,
                    "company_id": self.env.company.id,
                },
                **extra,
            )
        )
        slip.compute_sheet()
        return slip

    def test_ferias_pela_media_das_horas(self):
        emp, contract = self._horista()
        media = self._historico_2024(emp, contract)
        ferias = self._slip(
            emp, contract, self.structure_ferias, date(2025, 1, 1), date(2025, 1, 30)
        )
        self.assertGreater(media, 0)
        self.assertNotEqual(media, contract.wage)
        self.assertAlmostEqualMoney(self._get_line_total(ferias, "FERIAS"), media)

    def test_reajuste_do_valor_hora_atualiza_a_media(self):
        emp, contract = self._horista()
        media = self._historico_2024(emp, contract)
        contract.l10n_br_valor_hora = VALOR_HORA * 1.1
        ferias = self._slip(
            emp, contract, self.structure_ferias, date(2025, 1, 1), date(2025, 1, 30)
        )
        self.assertAlmostEqualMoney(
            self._get_line_total(ferias, "FERIAS"), media * 1.1, places=1
        )

    def test_13_primeira_segunda_e_integral(self):
        emp, contract = self._horista()
        self._historico_2024(emp, contract)
        primeira = self._slip(
            emp,
            contract,
            self.structure_13_primeira,
            date(2025, 11, 1),
            date(2025, 11, 30),
        )
        # Admitido em 2024: 12 avos em 2025; sem mensal confirmado em 2025, vale
        # a janela do ano (vazia) e as horas do próprio holerite.
        self.assertTrue(self._get_line_total(primeira, "ADIANTAMENTO_13") > 0)
        for estrutura in (self.structure_13_segunda, self.structure_13):
            slip = self._slip(
                emp, contract, estrutura, date(2024, 12, 1), date(2024, 12, 31)
            )
            # O mensal de dezembro é deste mesmo período: fica de fora (só os
            # mensais anteriores à competência entram).
            self.assertAlmostEqualMoney(
                self._get_line_total(slip, "DECIMO_TERCEIRO_BRUTO"),
                self.media_ate_novembro,
            )

    def test_primeira_parcela_pela_media_do_ano(self):
        emp, contract = self._horista()
        remuneracoes = []
        for mes in range(1, 11):
            slip = self._mensal(emp, contract, 2024, mes, 100.0 + 10 * mes)
            remuneracoes.append(
                self._get_line_total(slip, "SALARIO_BASE")
                + self._get_line_total(slip, "DSR_HORISTA")
            )
        media = round_money(sum(remuneracoes) / len(remuneracoes))
        primeira = self._slip(
            emp,
            contract,
            self.structure_13_primeira,
            date(2024, 11, 1),
            date(2024, 11, 30),
        )
        self.assertAlmostEqualMoney(
            self._get_line_total(primeira, "ADIANTAMENTO_13"), media * 0.5
        )

    def test_rescisao_horista_pela_media(self):
        emp, contract = self._horista()
        remuneracoes = []
        for mes in range(1, 6):
            slip = self._mensal(emp, contract, 2025, mes, 80.0 + 20 * mes)
            remuneracoes.append(
                self._get_line_total(slip, "SALARIO_BASE")
                + self._get_line_total(slip, "DSR_HORISTA")
            )
        media = self._media(remuneracoes)
        rescisao = self._slip(
            emp,
            contract,
            self.structure_rescisao,
            date(2025, 6, 1),
            date(2025, 6, 30),
            l10n_br_horas_pagas=40.0,
        )
        # Saldo: 40 h x R$ 20 mais o repouso do mês.
        self.assertAlmostEqualMoney(
            self._get_line_total(rescisao, "SALDO_SALARIO"),
            round_money(40 * VALOR_HORA + rescisao._l10n_br_dsr_horista()),
        )
        avos = rescisao.l10n_br_avos_ferias
        self.assertGreater(avos, 0)
        self.assertAlmostEqualMoney(
            self._get_line_total(rescisao, "FERIAS_INDENIZADAS"),
            round_money(media * avos / 12),
            places=1,
        )
        self.assertAlmostEqualMoney(
            self._get_line_total(rescisao, "DECIMO_RESCISAO"),
            round_money(media * rescisao.l10n_br_avos_13 / 12),
            places=1,
        )

    def test_jornada_parcial_desligado_no_primeiro_mes(self):
        """Sem mensal confirmado, valem as horas do próprio holerite.

        O mensal de referência (valor da hora x divisor da jornada) pagaria a
        mais quem tem jornada menor e sai nos primeiros meses.
        """
        calendario = self.env["resource.calendar"].create(
            {
                "name": "20h semanais",
                "attendance_ids": [
                    (
                        0,
                        0,
                        {
                            "name": "seg",
                            "dayofweek": "0",
                            "hour_from": 8,
                            "hour_to": 12,
                        },
                    ),
                    (
                        0,
                        0,
                        {
                            "name": "ter",
                            "dayofweek": "1",
                            "hour_from": 8,
                            "hour_to": 12,
                        },
                    ),
                    (
                        0,
                        0,
                        {
                            "name": "qua",
                            "dayofweek": "2",
                            "hour_from": 8,
                            "hour_to": 12,
                        },
                    ),
                    (
                        0,
                        0,
                        {
                            "name": "qui",
                            "dayofweek": "3",
                            "hour_from": 8,
                            "hour_to": 12,
                        },
                    ),
                    (
                        0,
                        0,
                        {
                            "name": "sex",
                            "dayofweek": "4",
                            "hour_from": 8,
                            "hour_to": 12,
                        },
                    ),
                ],
            }
        )
        emp, contract = self._horista(
            date_start=date(2024, 9, 1), calendario=calendario
        )
        self.assertEqual(contract._l10n_br_divisor_horas_mensais(), 100.0)
        mensal = self._mensal(emp, contract, 2024, 9, 60.0)
        rescisao = self._slip(
            emp,
            contract,
            self.structure_rescisao,
            date(2024, 9, 1),
            date(2024, 9, 30),
            l10n_br_horas_pagas=60.0,
        )
        referencia = round_money(60 * VALOR_HORA + mensal._l10n_br_dsr_horista())
        self.assertEqual(
            rescisao._l10n_br_salario_referencia(contract, "ferias_proporcionais"),
            referencia,
        )
        self.assertLess(referencia, contract.wage)
        self.assertEqual(rescisao.l10n_br_avos_ferias, 1)
        self.assertAlmostEqualMoney(
            self._get_line_total(rescisao, "FERIAS_INDENIZADAS"),
            round_money(referencia / 12),
            places=1,
        )

    def test_sem_hora_nenhuma_vale_o_mensal_de_referencia(self):
        emp, contract = self._horista()
        slip = self.env["hr.payslip"].create(
            {
                "name": "Sem hora",
                "employee_id": emp.id,
                "contract_id": contract.id,
                "struct_id": self.structure_ferias.id,
                "date_from": date(2024, 6, 1),
                "date_to": date(2024, 6, 30),
                "company_id": self.env.company.id,
            }
        )
        slip.worked_days_line_ids.unlink()
        self.assertEqual(slip._l10n_br_horas_do_horista(), 0.0)
        self.assertEqual(
            slip._l10n_br_salario_referencia(contract, "ferias"), contract.wage
        )

    def test_mensalista_inalterado(self):
        emp = self._create_employee("Mensalista")
        contract = self._create_contract(emp, wage=3000.0)
        slip = self._slip(
            emp, contract, self.structure_ferias, date(2025, 1, 1), date(2025, 1, 30)
        )
        self.assertEqual(slip._l10n_br_salario_referencia(contract, "ferias"), 3000.0)
        self.assertAlmostEqualMoney(self._get_line_total(slip, "FERIAS"), 3000.0)

    def test_aberto_recalcula_e_confirmado_nao_muda(self):
        emp, contract = self._horista()
        self._historico_2024(emp, contract)
        ferias = self._slip(
            emp, contract, self.structure_ferias, date(2025, 1, 1), date(2025, 1, 30)
        )
        antes = self._get_line_total(ferias, "FERIAS")
        contract.l10n_br_valor_hora = VALOR_HORA * 2
        ferias.compute_sheet()
        aberto = self._get_line_total(ferias, "FERIAS")
        self.assertAlmostEqualMoney(aberto, antes * 2, places=1)
        ferias.action_payslip_done()
        contract.l10n_br_valor_hora = VALOR_HORA * 3
        with self.assertRaises(UserError):
            ferias.compute_sheet()
        self.assertAlmostEqualMoney(self._get_line_total(ferias, "FERIAS"), aberto)
