# Copyright 2026 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""TG-166: horista: salário = horas x valor-hora e repouso semanal remunerado."""

import importlib.util
from datetime import date

from odoo.exceptions import ValidationError
from odoo.tests import tagged
from odoo.tools import file_path, mute_logger

from odoo.addons.l10n_br_hr_payroll.models.salary_rules_br import calc_dsr_horista

from .test_dsr_reflexo import OUT_2026, BaseDsrReflexo

NOV_2026 = dict(date_from=date(2026, 11, 1), date_to=date(2026, 11, 30))
VALOR_HORA = 20.0


class TestCalcDsrHorista(BaseDsrReflexo):
    def test_formula(self):
        # 176 h / 26 dias úteis x 5 repousos x R$ 20
        self.assertEqual(calc_dsr_horista(176.0, 20.0, 26, 5), 676.92)

    def test_sem_hora_valor_ou_dia_util(self):
        self.assertEqual(calc_dsr_horista(0.0, 20.0, 26, 5), 0.0)
        self.assertEqual(calc_dsr_horista(176.0, 0.0, 26, 5), 0.0)
        self.assertEqual(calc_dsr_horista(176.0, 20.0, 0, 5), 0.0)


class TestDsrHorista(BaseDsrReflexo):
    def _horista(self, calendario=None, periodo=None, **campos):
        emp = self._create_employee()
        contract = self._create_contract(emp, wage=3500.0)
        contract.write(
            {"l10n_br_unidade_salario": "hora", "l10n_br_valor_hora": VALOR_HORA}
        )
        if calendario:
            contract.resource_calendar_id = calendario
        slip = self._create_payslip(emp, contract, **(periodo or OUT_2026))
        faltas = campos.pop("faltas", ())
        slip.write(campos)
        if faltas:
            slip.write(
                {
                    "l10n_br_faltas_injustificadas": len(faltas),
                    "l10n_br_falta_ids": [(0, 0, {"date": d}) for d in faltas],
                }
            )
        slip.compute_sheet()
        return slip

    def test_mes_de_quatro_domingos_com_feriado(self):
        cal = self._calendario()
        self._feriado(cal)
        slip = self._horista(cal, l10n_br_horas_pagas=176.0)
        self.assertAlmostEqualMoney(
            self._get_line_total(slip, "SALARIO_BASE"), 176.0 * VALOR_HORA
        )
        self.assertAlmostEqualMoney(
            self._get_line_total(slip, "DSR_HORISTA"),
            round(176.0 / 26 * 5 * VALOR_HORA, 2),
        )

    def test_mes_de_cinco_domingos(self):
        cal = self._calendario()
        slip = self._horista(cal, NOV_2026, l10n_br_horas_pagas=176.0)
        self.assertAlmostEqualMoney(
            self._get_line_total(slip, "DSR_HORISTA"),
            round(176.0 / 25 * 5 * VALOR_HORA, 2),
        )

    def test_mes_de_quatro_domingos_sem_feriado(self):
        cal = self._calendario()
        slip = self._horista(cal, l10n_br_horas_pagas=176.0)
        self.assertAlmostEqualMoney(
            self._get_line_total(slip, "DSR_HORISTA"),
            round(176.0 / 27 * 4 * VALOR_HORA, 2),
        )

    def test_sem_horas_pagas_usa_as_horas_trabalhadas_do_periodo(self):
        cal = self._calendario()
        slip = self._horista(cal)
        horas = sum(
            slip.worked_days_line_ids.filtered(lambda w: w.code == "WORK100").mapped(
                "number_of_hours"
            )
        )
        self.assertAlmostEqualMoney(
            self._get_line_total(slip, "SALARIO_BASE"), round(horas * VALOR_HORA, 2)
        )

    def test_falta_na_semana_perde_um_dia_de_repouso_e_nao_desconta_salario(self):
        cal = self._calendario()
        self._feriado(cal)
        sem = self._horista(cal, l10n_br_horas_pagas=168.0)
        com = self._horista(cal, l10n_br_horas_pagas=168.0, faltas=[date(2026, 10, 6)])
        dsr = self._get_line_total(com, "DSR_HORISTA")
        self.assertEqual(dsr, self._get_line_total(sem, "DSR_HORISTA"))
        self.assertAlmostEqualMoney(
            self._get_line_total(com, "DESC_DSR"), round(dsr / 5, 2)
        )
        # as horas pagas já excluem a falta: não há desconto em dobro
        self.assertFalse(self._get_line_total(com, "FALTAS"))

    def test_horista_com_he_tem_repouso_e_reflexo(self):
        cal = self._calendario()
        self._feriado(cal)
        slip = self._horista(
            cal, l10n_br_horas_pagas=176.0, l10n_br_horas_extras_50=10.0
        )
        he = self._get_line_total(slip, "HE_50")
        self.assertAlmostEqualMoney(he, round(VALOR_HORA * 1.5 * 10, 2))
        self.assertAlmostEqualMoney(
            self._get_line_total(slip, "DSR_HE"), round(he / 26 * 5, 2)
        )
        self.assertTrue(self._get_line_total(slip, "DSR_HORISTA"))

    def test_mensalista_sem_mudanca(self):
        cal = self._calendario()
        self._feriado(cal)
        slip = self._holerite(cal, l10n_br_horas_extras_50=10.0)
        self.assertAlmostEqualMoney(self._get_line_total(slip, "SALARIO_BASE"), 3500.0)
        self.assertFalse(slip.line_ids.filtered(lambda ln: ln.code == "DSR_HORISTA"))
        horas = slip.contract_id._l10n_br_divisor_horas_mensais()
        self.assertAlmostEqualMoney(
            self._get_line_total(slip, "HE_50"), round(3500.0 / horas * 1.5 * 10, 2)
        )

    def test_confirmado_nao_muda_e_aberto_recalcula(self):
        cal = self._calendario()
        slip = self._horista(cal, l10n_br_horas_pagas=176.0)
        antes = self._get_line_total(slip, "DSR_HORISTA")
        slip.l10n_br_horas_pagas = 160.0
        slip.compute_sheet()
        self.assertNotEqual(self._get_line_total(slip, "DSR_HORISTA"), antes)
        slip.action_payslip_done()
        confirmado = self._get_line_total(slip, "DSR_HORISTA")
        slip.contract_id.l10n_br_valor_hora = 30.0
        self.assertEqual(self._get_line_total(slip, "DSR_HORISTA"), confirmado)

    def test_und_sal_fixo_e_vr_sal_fixo(self):
        emp = self._create_employee()
        contract = self._create_contract(emp, wage=3500.0)
        self.assertEqual(contract._l10n_br_und_sal_fixo(), 5)
        self.assertEqual(contract._l10n_br_vr_sal_fixo(), 3500.0)
        contract.write(
            {"l10n_br_unidade_salario": "hora", "l10n_br_valor_hora": VALOR_HORA}
        )
        self.assertEqual(contract._l10n_br_und_sal_fixo(), 1)
        self.assertEqual(contract._l10n_br_vr_sal_fixo(), VALOR_HORA)
        self.assertEqual(contract._l10n_br_salario_hora(), VALOR_HORA)

    def test_wage_do_horista_e_o_mensal_de_referencia(self):
        emp = self._create_employee()
        contract = self._create_contract(emp, wage=1.0)
        contract.write(
            {"l10n_br_unidade_salario": "hora", "l10n_br_valor_hora": VALOR_HORA}
        )
        divisor = contract._l10n_br_divisor_horas_mensais()
        self.assertAlmostEqualMoney(contract.wage, VALOR_HORA * divisor)
        # o mensal não é editável à mão: volta ao de referência
        contract.wage = 99.0
        self.assertAlmostEqualMoney(contract.wage, VALOR_HORA * divisor)
        # mudou o valor da hora: o mensal acompanha
        contract.l10n_br_valor_hora = 30.0
        self.assertAlmostEqualMoney(contract.wage, 30.0 * divisor)
        # o mensalista fica como está
        contract.l10n_br_unidade_salario = "mes"
        contract.wage = 3500.0
        self.assertEqual(contract.wage, 3500.0)

    def test_contrato_criado_ja_como_horista(self):
        emp = self._create_employee()
        contract = self.env["hr.contract"].create(
            {
                "name": "Horista",
                "employee_id": emp.id,
                "wage": 1.0,
                "l10n_br_unidade_salario": "hora",
                "l10n_br_valor_hora": VALOR_HORA,
                "date_start": "2024-01-01",
                "state": "open",
                "struct_id": self.structure_clt.id,
            }
        )
        self.assertAlmostEqualMoney(
            contract.wage, VALOR_HORA * contract._l10n_br_divisor_horas_mensais()
        )

    def test_horista_sem_valor_hora_e_recusado(self):
        emp = self._create_employee()
        contract = self._create_contract(emp, wage=3500.0)
        with self.assertRaises(ValidationError):
            contract.l10n_br_unidade_salario = "hora"

    def test_periculosidade_do_horista_sobre_o_mensal_de_referencia(self):
        cal = self._calendario()
        slip = self._horista(cal, l10n_br_horas_pagas=176.0)
        contract = slip.contract_id
        contract.l10n_br_periculosidade = True
        slip.compute_sheet()
        mensal = contract.wage
        self.assertGreaterEqual(mensal, 20.0 * 176)
        self.assertAlmostEqualMoney(
            self._get_line_total(slip, "ADICIONAL_PERICULOSIDADE"),
            round(mensal * 0.30, 2),
        )
        self.assertGreaterEqual(
            self._get_line_total(slip, "ADICIONAL_PERICULOSIDADE"), 1056.0
        )

    def test_falta_sem_horas_pagas_desconta_as_horas(self):
        cal = self._calendario()
        sem = self._horista(cal)
        com = self._horista(cal, faltas=[date(2026, 10, 6), date(2026, 10, 7)])
        horas_dia = cal.hours_per_day or 8.0
        self.assertAlmostEqualMoney(
            self._get_line_total(sem, "SALARIO_BASE")
            - self._get_line_total(com, "SALARIO_BASE"),
            round(2 * horas_dia * VALOR_HORA, 2),
        )
        self.assertFalse(self._get_line_total(com, "FALTAS"))

    def test_falta_em_feriado_ou_domingo_nao_abate_horas(self):
        cal = self._calendario()
        self._feriado(cal)  # 12/10/2026, segunda-feira
        sem = self._horista(cal)
        feriado = self._horista(cal, faltas=[date(2026, 10, 12)])
        domingo = self._horista(cal, faltas=[date(2026, 10, 4)])
        base = self._get_line_total(sem, "SALARIO_BASE")
        self.assertAlmostEqualMoney(self._get_line_total(feriado, "SALARIO_BASE"), base)
        self.assertAlmostEqualMoney(self._get_line_total(domingo, "SALARIO_BASE"), base)
        # dia útil comum abate a jornada do dia
        util = self._horista(cal, faltas=[date(2026, 10, 13)])
        self.assertAlmostEqualMoney(
            base - self._get_line_total(util, "SALARIO_BASE"),
            round((cal.hours_per_day or 8.0) * VALOR_HORA, 2),
        )

    def test_feriado_no_domingo_nao_conta_em_dobro(self):
        cal = self._calendario()
        self._feriado(cal, dia=date(2026, 10, 4))
        slip = self._horista(cal, l10n_br_horas_pagas=176.0)
        self.assertAlmostEqualMoney(
            self._get_line_total(slip, "DSR_HORISTA"),
            round(176.0 / 27 * 4 * VALOR_HORA, 2),
        )


@tagged("post_install", "-at_install")
class TestMigracaoHorista(BaseDsrReflexo):
    _horista = TestDsrHorista._horista

    def _migrar(self):
        caminho = file_path(
            "l10n_br_hr_payroll/migrations/18.0.1.15.0/post-migration.py"
        )
        spec = importlib.util.spec_from_file_location("post_migration_tg166", caminho)
        modulo = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(modulo)
        with mute_logger("post_migration_tg166"):
            modulo.migrate(self.env.cr, "18.0.1.14.0")

    def _estado_1_14(self):
        """Fórmulas como o XML da 18.0.1.14.0 (9de402dd) as grava, com comentários."""
        ref = self.env.ref
        ref("l10n_br_hr_payroll.hr_rule_salario_base").amount_python_compute = (
            "\n# Proporcional aos dias de salário do mês (admissão, desligamento, "
            "afastamento\n"
            "# previdenciário), em mês comercial de 30 dias. Os dias de "
            "licença-maternidade\n"
            "# saem daqui e vão para SALARIO_MATERNIDADE (mesmo conjunto de dias).\n"
            "dias = tools.br.dias_salario(contract) - "
            "tools.br.dias_maternidade(contract)\n"
            "result = tools.br.round_money(contract.wage * dias / 30)\n        "
        )
        ref(
            "l10n_br_hr_payroll.hr_rule_faltas"
        ).condition_python = (
            "\nresult = payslip.l10n_br_faltas_injustificadas > 0\n        "
        )
        ref("l10n_br_hr_payroll.hr_rule_desc_dsr").amount_python_compute = (
            "\nresult = tools.br.round_money((contract.wage / 30) * "
            "tools.br.semanas_com_falta(contract))\n        "
        )
        for xmlid, resto in (
            (
                "hr_rule_he_50",
                "result = tools.br.round_money(salario_hora * 1.5 * "
                "payslip.l10n_br_horas_extras_50)",
            ),
            (
                "hr_rule_he_100",
                "result = tools.br.round_money(salario_hora * 2.0 * "
                "payslip.l10n_br_horas_extras_100)",
            ),
            (
                "hr_rule_adicional_noturno",
                "result = tools.br.round_money(salario_hora * "
                "contract.l10n_br_adicional_noturno_perc / 100.0 * "
                "payslip.l10n_br_horas_noturnas_computadas)",
            ),
        ):
            ref(f"l10n_br_hr_payroll.{xmlid}").amount_python_compute = (
                "\nsalario_hora = contract.wage / "
                "contract._l10n_br_divisor_horas_mensais()\n" + resto + "\n        "
            )
        ref("l10n_br_hr_payroll.structure_clt").rule_ids = [
            (3, ref("l10n_br_hr_payroll.hr_rule_dsr_horista").id)
        ]

    def test_banco_1_14_ganha_o_ramo_do_horista(self):
        self._estado_1_14()
        self._migrar()
        ref = self.env.ref
        self.assertIn(
            "_l10n_br_salario_hora()",
            ref("l10n_br_hr_payroll.hr_rule_he_50").amount_python_compute,
        )
        self.assertIn(
            "_l10n_br_horista()",
            ref("l10n_br_hr_payroll.hr_rule_faltas").condition_python,
        )
        base = ref("l10n_br_hr_payroll.hr_rule_salario_base").amount_python_compute
        self.assertIn("_l10n_br_salario_hora() * tools.br.horas_horista()", base)
        self.assertIn("contract.wage * dias / 30", base)
        self.assertIn(
            "_l10n_br_horista()",
            ref("l10n_br_hr_payroll.hr_rule_desc_dsr").amount_python_compute,
        )
        for xmlid in ("hr_rule_he_100", "hr_rule_adicional_noturno"):
            self.assertIn(
                "_l10n_br_salario_hora()",
                ref(f"l10n_br_hr_payroll.{xmlid}").amount_python_compute,
            )
        # o resultado vale no holerite: horista de R$ 20/h, 176 h, 40 h semanais
        slip = self._horista(self._calendario(), l10n_br_horas_pagas=176.0)
        self.assertAlmostEqualMoney(self._get_line_total(slip, "SALARIO_BASE"), 3520.0)
        self.assertIn(
            ref("l10n_br_hr_payroll.hr_rule_dsr_horista"),
            ref("l10n_br_hr_payroll.structure_clt").rule_ids,
        )

    def test_salario_base_personalizado_nao_e_trocado(self):
        self._estado_1_14()
        regra = self.env.ref("l10n_br_hr_payroll.hr_rule_salario_base")
        personalizada = regra.amount_python_compute.replace("dias / 30", "dias / 31")
        regra.amount_python_compute = personalizada
        self._migrar()
        self.assertEqual(regra.amount_python_compute, personalizada)

    def test_personalizada_fica_como_esta_e_idempotente(self):
        self._estado_1_14()
        faltas = self.env.ref("l10n_br_hr_payroll.hr_rule_faltas")
        faltas.condition_python = "result = True"
        self._migrar()
        self.assertEqual(faltas.condition_python, "result = True")
        he = self.env.ref("l10n_br_hr_payroll.hr_rule_he_50").amount_python_compute
        self._migrar()
        self.assertEqual(
            self.env.ref("l10n_br_hr_payroll.hr_rule_he_50").amount_python_compute, he
        )
