# Copyright 2024 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""TG-86: horas extras e adicional noturno refletem no DSR (Súmulas 172 e 60)."""

import importlib.util
from datetime import date, datetime

from odoo.tests.common import TransactionCase
from odoo.tools import file_path

from odoo.addons.l10n_br_hr_payroll.models.salary_rules_br import (
    calc_dsr_reflexo,
    dias_dsr,
)

from .common import PayrollCommon

OUT_2026 = dict(date_from=date(2026, 10, 1), date_to=date(2026, 10, 31))
FERIADO = date(2026, 10, 12)


class TestDiasDsrPuro(TransactionCase):
    """Dias úteis e de repouso do mês."""

    def test_so_domingos(self):
        # Outubro/2026: 31 dias, domingos 4, 11, 18 e 25.
        self.assertEqual(dias_dsr(2026, 10), (27, 4))

    def test_feriado_vira_repouso(self):
        self.assertEqual(dias_dsr(2026, 10, {FERIADO}), (26, 5))

    def test_feriado_no_domingo_nao_conta_duas_vezes(self):
        self.assertEqual(dias_dsr(2026, 10, {date(2026, 10, 4)}), (27, 4))

    def test_feriado_de_outro_mes_e_ignorado(self):
        self.assertEqual(dias_dsr(2026, 10, {date(2026, 11, 2)}), (27, 4))

    def test_reflexo(self):
        # P022 do gabarito: 360,00 de horas extras, 26 úteis, 5 repousos.
        self.assertEqual(calc_dsr_reflexo(360.0, 26, 5), 69.23)
        self.assertEqual(calc_dsr_reflexo(160.0, 26, 5), 30.77)

    def test_reflexo_sem_valor_ou_sem_dia_util(self):
        self.assertEqual(calc_dsr_reflexo(0.0, 26, 5), 0.0)
        self.assertEqual(calc_dsr_reflexo(100.0, 0, 5), 0.0)


class TestDsrReflexoHolerite(PayrollCommon):
    """Holerite mensal: DSR_HE e DSR_NOTURNO a partir das verbas do mês."""

    def _calendario(self, tz="America/Sao_Paulo"):
        return self.env["resource.calendar"].create(
            {"name": "Calendário DSR", "tz": tz}
        )

    def _feriado(self, calendario, dia=FERIADO, empresa=None, **extra):
        """Ausência global do dia inteiro (fuso de São Paulo = UTC-3)."""
        vals = {
            "name": "Feriado",
            "calendar_id": calendario.id if calendario else False,
            "company_id": (empresa or self.env.company).id,
            "date_from": datetime(dia.year, dia.month, dia.day, 3, 0, 0),
            "date_to": datetime(dia.year, dia.month, dia.day, 23, 59, 59),
        }
        vals.update(extra)
        return self.env["resource.calendar.leaves"].create(vals)

    def _holerite(self, calendario=None, **campos):
        emp = self._create_employee()
        contract = self._create_contract(emp, wage=3500.00)
        if calendario:
            contract.resource_calendar_id = calendario
        slip = self._create_payslip(emp, contract, **OUT_2026)
        slip.write(campos)
        slip.compute_sheet()
        return slip

    def test_dsr_sobre_horas_extras_com_feriado(self):
        cal = self._calendario()
        self._feriado(cal)
        slip = self._holerite(cal, l10n_br_horas_extras_50=10.0)
        he = self._get_line_total(slip, "HE_50")
        self.assertGreater(he, 0)
        self.assertAlmostEqualMoney(
            self._get_line_total(slip, "DSR_HE"), round(he / 26 * 5, 2)
        )

    def test_sem_feriado_so_domingos(self):
        cal = self._calendario()
        slip = self._holerite(cal, l10n_br_horas_extras_50=10.0)
        he = self._get_line_total(slip, "HE_50")
        self.assertAlmostEqualMoney(
            self._get_line_total(slip, "DSR_HE"), round(he / 27 * 4, 2)
        )

    def test_dsr_sobre_adicional_noturno(self):
        cal = self._calendario()
        self._feriado(cal)
        slip = self._holerite(
            cal, l10n_br_horas_noturnas=40.0, l10n_br_usar_hora_reduzida=True
        )
        noturno = self._get_line_total(slip, "ADICIONAL_NOTURNO")
        self.assertGreater(noturno, 0)
        self.assertAlmostEqualMoney(
            self._get_line_total(slip, "DSR_NOTURNO"), round(noturno / 26 * 5, 2)
        )
        self.assertFalse(slip.line_ids.filtered(lambda ln: ln.code == "DSR_HE"))

    def test_reflexo_entra_no_bruto_e_nas_bases(self):
        cal = self._calendario()
        self._feriado(cal)
        slip = self._holerite(
            cal, l10n_br_horas_extras_50=10.0, l10n_br_horas_noturnas=40.0
        )
        dsr = self._get_line_total(slip, "DSR_HE") + self._get_line_total(
            slip, "DSR_NOTURNO"
        )
        sem = (
            3500.00
            + self._get_line_total(slip, "HE_50")
            + self._get_line_total(slip, "ADICIONAL_NOTURNO")
        )
        self.assertAlmostEqualMoney(self._get_line_total(slip, "GROSS"), sem + dsr)
        # FGTS = 8% da base, que inclui o reflexo.
        self.assertAlmostEqualMoney(
            self._get_line_total(slip, "FGTS"), round((sem + dsr) * 0.08, 2)
        )

    def test_sem_horas_nao_gera_reflexo(self):
        slip = self._holerite()
        codes = slip.line_ids.mapped("code")
        self.assertNotIn("DSR_HE", codes)
        self.assertNotIn("DSR_NOTURNO", codes)

    def test_feriado_de_outro_calendario_ou_empresa_nao_conta(self):
        cal = self._calendario()
        outro = self._calendario()
        self._feriado(outro)
        empresa = self.env["res.company"].create({"name": "Outra empresa DSR"})
        # O Odoo recalcula a empresa da ausência pelo calendário ao criar.
        self._feriado(False, dia=date(2026, 10, 20)).company_id = empresa
        slip = self._holerite(cal, l10n_br_horas_extras_50=10.0)
        he = self._get_line_total(slip, "HE_50")
        self.assertAlmostEqualMoney(
            self._get_line_total(slip, "DSR_HE"), round(he / 27 * 4, 2)
        )

    def test_feriado_global_sem_calendario_vale_para_todos(self):
        cal = self._calendario()
        self._feriado(False)
        slip = self._holerite(cal, l10n_br_horas_extras_50=10.0)
        he = self._get_line_total(slip, "HE_50")
        self.assertAlmostEqualMoney(
            self._get_line_total(slip, "DSR_HE"), round(he / 26 * 5, 2)
        )

    def test_ausencia_de_um_empregado_nao_e_feriado(self):
        cal = self._calendario()
        emp = self._create_employee("Com ausência")
        self._feriado(cal, resource_id=emp.resource_id.id)
        slip = self._holerite(cal, l10n_br_horas_extras_50=10.0)
        he = self._get_line_total(slip, "HE_50")
        self.assertAlmostEqualMoney(
            self._get_line_total(slip, "DSR_HE"), round(he / 27 * 4, 2)
        )


class TestMigracaoDsr(PayrollCommon):
    """A migração liga as rubricas à estrutura CLT, uma vez e sem sobrepor."""

    def _migrar(self):
        caminho = file_path(
            "l10n_br_hr_payroll/migrations/18.0.1.5.0/post-migration.py"
        )
        spec = importlib.util.spec_from_file_location("post_migration_tg86", caminho)
        modulo = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(modulo)
        modulo.migrate(self.env.cr, "18.0.1.4.0")

    def test_liga_as_rubricas_de_forma_idempotente(self):
        regras = self.env.ref("l10n_br_hr_payroll.hr_rule_dsr_he") | self.env.ref(
            "l10n_br_hr_payroll.hr_rule_dsr_noturno"
        )
        self.structure_clt.write({"rule_ids": [(3, r.id) for r in regras]})
        self.assertFalse(set(regras.ids) & set(self.structure_clt.rule_ids.ids))
        self._migrar()
        self._migrar()
        self.assertTrue(set(regras.ids) <= set(self.structure_clt.rule_ids.ids))
        codigos = self.structure_clt.rule_ids.mapped("code")
        self.assertEqual(codigos.count("DSR_HE"), 1)
        self.assertEqual(codigos.count("DSR_NOTURNO"), 1)

    def test_nao_duplica_rubrica_de_mesmo_codigo(self):
        padrao = self.env.ref("l10n_br_hr_payroll.hr_rule_dsr_he")
        outra = padrao.copy({"name": "DSR HE do ponto"})
        self.structure_clt.write({"rule_ids": [(3, padrao.id), (4, outra.id)]})
        self._migrar()
        self.assertEqual(self.structure_clt.rule_ids.mapped("code").count("DSR_HE"), 1)
        self.assertIn(outra, self.structure_clt.rule_ids)
