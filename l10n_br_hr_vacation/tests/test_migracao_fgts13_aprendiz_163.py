# Copyright 2026 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""TG-163: a migração 18.0.1.18.0 tira do FGTS do 13º a condição que exclui o aprendiz.

Banco vindo da 1.8.0 ou da 1.9.0: a 1.10.0 grava a fórmula atual e a 1.14.0 a vê
"já atualizada", deixando a condição ``!= 'aprendiz'`` e a rescisão do aprendiz
sem FGTS do 13º.
"""
import importlib.util
from datetime import date, timedelta

from dateutil.relativedelta import relativedelta

from odoo.tests import tagged
from odoo.tools import file_path

from odoo.addons.l10n_br_hr_payroll.models.salary_rules_br import round_money

from .common import VacationCommon

# Como o XML da 1.8.0/1.9.0 grava a condição (com quebras de linha em volta).
CONDICAO_ANTIGA = "\nresult = employee.l10n_br_tipo_contrato != 'aprendiz'\n        "
XMLIDS = ("hr_rule_fgts_13_primeira", "hr_rule_fgts_13", "hr_rule_fgts_13_rescisao")
LOGGER = "mig_163"


@tagged("post_install", "-at_install")
class TestMigracaoFgts13Aprendiz163(VacationCommon):
    exigir_alocacao_periodo = True

    def _regra(self, xmlid):
        return self.env.ref(f"l10n_br_hr_vacation.{xmlid}")

    def _para_1_9(self):
        """Estado que a 1.10.0 + 1.14.0 deixam: fórmula atual, condição antiga."""
        for xmlid in XMLIDS:
            self._regra(xmlid).write(
                {"condition_select": "python", "condition_python": CONDICAO_ANTIGA}
            )

    def _migrar(self):
        caminho = file_path(
            "l10n_br_hr_vacation/migrations/18.0.1.18.0/post-migration.py"
        )
        spec = importlib.util.spec_from_file_location(LOGGER, caminho)
        modulo = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(modulo)
        modulo.migrate(self.env.cr, "18.0.1.17.0")

    def _rescisao_aprendiz(self):
        emp = self._create_employee("Aprendiz FGTS 13º")
        emp.l10n_br_tipo_contrato = "aprendiz"
        contract = self._create_contract(emp, wage=2500.00, date_start=date(2020, 1, 1))
        ate = date(2026, 12, 10)
        anos = relativedelta(ate + timedelta(days=1), contract.date_start).years
        self.env["hr.leave.allocation"].create(
            {
                "employee_id": emp.id,
                "holiday_status_id": self.leave_type_ferias.id,
                "date_from": contract.date_start + relativedelta(years=anos - 1),
                "date_to": contract.date_start
                + relativedelta(years=anos)
                - timedelta(days=1),
            }
        ).action_validate()
        slip = self.env["hr.payslip"].create(
            {
                "name": "Rescisão aprendiz",
                "employee_id": emp.id,
                "contract_id": contract.id,
                "struct_id": self.structure_rescisao.id,
                "date_from": ate.replace(day=1),
                "date_to": ate,
                "company_id": self.env.company.id,
                "l10n_br_tipo_rescisao": "sem_justa_causa",
                "l10n_br_aviso_previo": "trabalhado",
                "l10n_br_fgts_saldo_conta": 10000.00,
            }
        )
        slip.compute_sheet()
        return slip

    def test_banco_da_1_9_perde_a_condicao_e_o_aprendiz_recebe_o_fgts_13(self):
        self._para_1_9()
        antes = self._rescisao_aprendiz()
        self.assertEqual(self._get_line_total(antes, "FGTS_13"), 0)
        devido = self._get_line_total(antes, "DECIMO_DEVIDO")
        self.assertGreater(devido, 0)
        self._migrar()
        for xmlid in XMLIDS:
            self.assertEqual(self._regra(xmlid).condition_select, "none", xmlid)
        antes.compute_sheet()
        self.assertAlmostEqualMoney(
            self._get_line_total(antes, "FGTS_13"), round_money(devido * 0.02)
        )

    def test_banco_atual_fica_igual_e_sem_aviso(self):
        antes = {x: self._regra(x).read()[0] for x in XMLIDS}
        with self.assertNoLogs(LOGGER, "WARNING"):
            self._migrar()
        for xmlid in XMLIDS:
            self.assertEqual(self._regra(xmlid).read()[0], antes[xmlid], xmlid)

    def test_migracao_e_idempotente(self):
        self._para_1_9()
        self._migrar()
        apos = {x: self._regra(x).read()[0] for x in XMLIDS}
        self._migrar()
        for xmlid in XMLIDS:
            self.assertEqual(self._regra(xmlid).read()[0], apos[xmlid], xmlid)

    def test_condicao_personalizada_e_mantida_sem_warning(self):
        self._para_1_9()
        regra = self._regra("hr_rule_fgts_13_rescisao")
        propria = "result = employee.l10n_br_tipo_contrato == 'clt'"
        regra.condition_python = propria
        with self.assertLogs(LOGGER, "INFO") as logs:
            self._migrar()
        self.assertTrue(
            any("personalizada" in saida for saida in logs.output), logs.output
        )
        self.assertFalse(
            any(saida.startswith("WARNING") for saida in logs.output), logs.output
        )
        self.assertEqual(regra.condition_select, "python")
        self.assertEqual(regra.condition_python, propria)
        # As outras duas, com a condição padrão antiga, são atualizadas.
        for xmlid in ("hr_rule_fgts_13_primeira", "hr_rule_fgts_13"):
            self.assertEqual(self._regra(xmlid).condition_select, "none")

    def test_formula_personalizada_nao_perde_a_condicao(self):
        self._para_1_9()
        regra = self._regra("hr_rule_fgts_13")
        regra.amount_python_compute = "result = 1.0"
        self._migrar()
        self.assertEqual(regra.condition_select, "python")
        self.assertEqual(regra.amount_python_compute, "result = 1.0")
