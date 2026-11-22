# Copyright 2026 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""TG-166: horista: salário = horas x valor-hora e repouso semanal remunerado."""

import importlib.util
from datetime import date

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
        contract = self._create_contract(emp, wage=VALOR_HORA)
        contract.l10n_br_unidade_salario = "hora"
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
        slip.contract_id.wage = 30.0
        self.assertEqual(self._get_line_total(slip, "DSR_HORISTA"), confirmado)

    def test_und_sal_fixo(self):
        emp = self._create_employee()
        contract = self._create_contract(emp, wage=VALOR_HORA)
        self.assertEqual(contract._l10n_br_und_sal_fixo(), 5)
        contract.l10n_br_unidade_salario = "hora"
        self.assertEqual(contract._l10n_br_und_sal_fixo(), 1)
        self.assertEqual(contract._l10n_br_salario_hora(), VALOR_HORA)


@tagged("post_install", "-at_install")
class TestMigracaoHorista(BaseDsrReflexo):
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
        ref = self.env.ref
        ref("l10n_br_hr_payroll.hr_rule_he_50").amount_python_compute = (
            "salario_hora = contract.wage / contract._l10n_br_divisor_horas_mensais()\n"
            "result = tools.br.round_money(salario_hora * 1.5 * payslip.l10n_br_horas_extras_50)"  # noqa: B950
        )
        ref(
            "l10n_br_hr_payroll.hr_rule_faltas"
        ).condition_python = "result = payslip.l10n_br_faltas_injustificadas > 0"
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
        self.assertIn(
            ref("l10n_br_hr_payroll.hr_rule_dsr_horista"),
            ref("l10n_br_hr_payroll.structure_clt").rule_ids,
        )

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
