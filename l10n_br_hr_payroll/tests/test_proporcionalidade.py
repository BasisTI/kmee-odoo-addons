# Copyright 2024 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""Proporcionalidade do salário: admissão, desligamento e afastamento (TG-82).

Casos de referência: gabarito da POC (P009, P010, P011), outubro/2026.
"""
import importlib.util
from datetime import date
from pathlib import Path

from odoo.tests.common import BaseCase

from ..models.salary_rules_br import dias_salario_mes
from .common import PayrollCommon

OUT_INI, OUT_FIM = date(2026, 10, 1), date(2026, 10, 31)


class TestDiasSalarioMes(BaseCase):
    """Função pura: dias de salário no mês comercial de 30 dias."""

    def test_mes_cheio_e_30(self):
        self.assertEqual(dias_salario_mes(OUT_INI, OUT_FIM), 30)

    def test_fevereiro_cheio_e_30(self):
        self.assertEqual(dias_salario_mes(date(2026, 2, 1), date(2026, 2, 28)), 30)

    def test_admissao_em_15_10_paga_17_dias(self):
        self.assertEqual(
            dias_salario_mes(OUT_INI, OUT_FIM, data_admissao=date(2026, 10, 15)), 17
        )

    def test_desligamento_em_20_10_paga_20_dias(self):
        self.assertEqual(
            dias_salario_mes(OUT_INI, OUT_FIM, data_demissao=date(2026, 10, 20)), 20
        )

    def test_afastamento_5_a_26_10_desconta_7_dias_do_inss(self):
        """22 dias de afastamento: 15 da empresa, 7 do INSS."""
        self.assertEqual(
            dias_salario_mes(
                OUT_INI,
                OUT_FIM,
                afastamentos_inss=[(date(2026, 10, 5), date(2026, 10, 26))],
            ),
            23,
        )

    def test_afastamento_ate_15_dias_nao_desconta(self):
        self.assertEqual(
            dias_salario_mes(
                OUT_INI,
                OUT_FIM,
                afastamentos_inss=[(date(2026, 10, 5), date(2026, 10, 19))],
            ),
            30,
        )

    def test_afastamento_iniciado_no_mes_anterior(self):
        """Início em 20/09: o 16º dia é 05/10; de 05 a 10/10 são 6 dias do INSS."""
        self.assertEqual(
            dias_salario_mes(
                OUT_INI,
                OUT_FIM,
                afastamentos_inss=[(date(2026, 9, 20), date(2026, 10, 10))],
            ),
            24,
        )

    def test_contrato_fora_do_periodo(self):
        self.assertEqual(
            dias_salario_mes(OUT_INI, OUT_FIM, data_demissao=date(2026, 9, 30)), 0
        )

    def _afast(self, inicio, fim, periodo=OUT_FIM, ini_periodo=OUT_INI, **kw):
        return dias_salario_mes(
            ini_periodo, periodo, afastamentos_inss=[(inicio, fim)], **kw
        )

    def test_classe_fevereiro_afastado_do_dia_1_ao_ultimo_paga_15(self):
        self.assertEqual(
            self._afast(
                date(2026, 2, 1), date(2026, 2, 28), date(2026, 2, 28), date(2026, 2, 1)
            ),
            15,
        )
        self.assertEqual(
            self._afast(
                date(2028, 2, 1), date(2028, 2, 29), date(2028, 2, 29), date(2028, 2, 1)
            ),
            15,
        )

    def test_classe_mes_de_31_afastado_do_dia_1_ao_31_paga_15(self):
        self.assertEqual(self._afast(date(2026, 10, 1), date(2026, 10, 31)), 15)

    def test_classe_16o_dia_neste_mes_paga_ate_o_15o(self):
        """Início em 25/09: o 15º dia é 09/10; a empresa paga 1 a 9/10."""
        self.assertEqual(self._afast(date(2026, 9, 25), date(2026, 10, 31)), 9)

    def test_classe_afastamento_com_dias_sobrepostos_nao_duplica(self):
        dias = dias_salario_mes(
            OUT_INI,
            OUT_FIM,
            afastamentos_inss=[
                (date(2026, 10, 1), date(2026, 10, 31)),
                (date(2026, 10, 10), date(2026, 10, 31)),
            ],
        )
        self.assertEqual(dias, 15)

    def test_classe_admissao_no_mesmo_mes_do_afastamento(self):
        """Admitido 15/10 (17 dias) e afastado 16 a 31/10: INSS só em 31/10."""
        self.assertEqual(
            self._afast(
                date(2026, 10, 16), date(2026, 10, 31), data_admissao=date(2026, 10, 15)
            ),
            16,
        )

    def test_classe_desligamento_no_mesmo_mes_do_afastamento(self):
        """Desligado 20/10 e afastado de 1 a 20/10: 15 da empresa, 5 do INSS."""
        self.assertEqual(
            self._afast(
                date(2026, 10, 1), date(2026, 10, 20), data_demissao=date(2026, 10, 20)
            ),
            15,
        )

    def test_fevereiro_inteiro_de_inss_paga_zero(self):
        for ano, ultimo in ((2026, 28), (2028, 29)):
            self.assertEqual(
                dias_salario_mes(
                    date(ano, 2, 1),
                    date(ano, 2, ultimo),
                    afastamentos_inss=[(date(ano, 1, 1), date(ano, 3, 31))],
                ),
                0,
                ano,
            )

    def test_mes_de_31_dias_inteiro_de_inss_paga_zero(self):
        self.assertEqual(
            dias_salario_mes(
                OUT_INI,
                OUT_FIM,
                afastamentos_inss=[(date(2026, 9, 1), date(2026, 11, 30))],
            ),
            0,
        )

    def test_mes_de_31_dias_dia_31_nao_tem_correspondente_comercial(self):
        self.assertEqual(
            dias_salario_mes(
                OUT_INI,
                OUT_FIM,
                afastamentos_inss=[(date(2026, 9, 17), date(2026, 11, 30))],
            ),
            1,
        )
        self.assertEqual(
            dias_salario_mes(
                OUT_INI,
                OUT_FIM,
                afastamentos_inss=[(date(2026, 9, 17), date(2026, 10, 30))],
            ),
            1,
        )

    def test_fevereiro_so_o_dia_1_da_empresa_paga_um(self):
        """Início em 18/01: o 15º dia é 01/02; INSS de 2 a 28/02."""
        self.assertEqual(
            dias_salario_mes(
                date(2026, 2, 1),
                date(2026, 2, 28),
                afastamentos_inss=[(date(2026, 1, 18), date(2026, 2, 28))],
            ),
            1,
        )

    def test_fevereiro_so_o_ultimo_dia_trabalhado_vale_3_dias_comerciais(self):
        """O dia 28/02 é o dia 30 comercial (vale também 29 e 30)."""
        self.assertEqual(
            dias_salario_mes(
                date(2026, 2, 1),
                date(2026, 2, 28),
                afastamentos_inss=[(date(2026, 1, 1), date(2026, 2, 27))],
            ),
            3,
        )


class TestDiasSalarioFerias(BaseCase):
    """Férias gozadas (TG-83): os dias já pagos no recibo saem do salário do mês."""

    NOV_INI, NOV_FIM = date(2026, 11, 1), date(2026, 11, 30)

    def _dias(self, ferias, ini=None, fim=None, **kw):
        return dias_salario_mes(
            ini or self.NOV_INI, fim or self.NOV_FIM, ferias_gozadas=ferias, **kw
        )

    def test_sem_ferias_nao_muda(self):
        self.assertEqual(self._dias([]), 30)

    def test_10_dias_no_meio_do_mes(self):
        """M01: férias de 16 a 25/11 deixam 20 dias de salário."""
        self.assertEqual(self._dias([(date(2026, 11, 16), date(2026, 11, 25))]), 20)

    def test_mes_inteiro_em_ferias_paga_zero(self):
        """M02: férias de 01 a 30/11 não deixam salário."""
        self.assertEqual(self._dias([(date(2026, 11, 1), date(2026, 11, 30))]), 0)

    def test_ferias_comecando_no_meio_e_terminando_no_proximo_mes(self):
        """Férias de 20/11 a 09/12: novembro perde 11 dias; dezembro, 9."""
        ferias = [(date(2026, 11, 20), date(2026, 12, 9))]
        self.assertEqual(self._dias(ferias), 19)
        self.assertEqual(self._dias(ferias, date(2026, 12, 1), date(2026, 12, 31)), 21)

    def test_ferias_comecadas_no_mes_anterior(self):
        """Férias de 25/10 a 13/11: novembro perde 13 dias."""
        self.assertEqual(self._dias([(date(2026, 10, 25), date(2026, 11, 13))]), 17)

    def test_mes_de_31_dias_inteiro_em_ferias_paga_zero(self):
        """O dia 31 não tem correspondente comercial: 1 a 31/12 também zera."""
        self.assertEqual(
            self._dias(
                [(date(2026, 12, 1), date(2026, 12, 31))],
                date(2026, 12, 1),
                date(2026, 12, 31),
            ),
            0,
        )

    def test_fevereiro_inteiro_em_ferias_paga_zero(self):
        self.assertEqual(
            self._dias(
                [(date(2026, 2, 1), date(2026, 2, 28))],
                date(2026, 2, 1),
                date(2026, 2, 28),
            ),
            0,
        )

    def test_ferias_ate_o_fim_de_fevereiro_valem_30_dias_comerciais(self):
        """Férias de 15 a 28/02 (14 dias civis) tiram 16 dias comerciais."""
        self.assertEqual(
            self._dias(
                [(date(2026, 2, 15), date(2026, 2, 28))],
                date(2026, 2, 1),
                date(2026, 2, 28),
            ),
            14,
        )

    def test_dias_de_ferias_e_de_inss_coincidentes_nao_saem_duas_vezes(self):
        """Afastamento de 01 a 30/11 (INSS do 16º ao 30º); férias de 20 a 25/11."""
        self.assertEqual(
            self._dias(
                [(date(2026, 11, 20), date(2026, 11, 25))],
                afastamentos_inss=[(date(2026, 11, 1), date(2026, 11, 30))],
            ),
            15,
        )

    def test_ferias_somadas_ao_afastamento_inss(self):
        """INSS de 16 a 20/11 (5 dias) e férias de 25 a 29/11 (5): paga 20."""
        self.assertEqual(
            self._dias(
                [(date(2026, 11, 25), date(2026, 11, 29))],
                afastamentos_inss=[(date(2026, 11, 1), date(2026, 11, 20))],
            ),
            20,
        )

    def test_ferias_na_admissao_no_meio_do_mes(self):
        """Admitido em 10/11, férias de 20 a 25/11: 21 dias de vigência, 6 de férias."""
        self.assertEqual(
            self._dias(
                [(date(2026, 11, 20), date(2026, 11, 25))],
                data_admissao=date(2026, 11, 10),
            ),
            15,
        )

    def test_ferias_fora_do_periodo_nao_descontam(self):
        self.assertEqual(self._dias([(date(2026, 12, 1), date(2026, 12, 10))]), 30)

    def test_nao_deixa_negativo(self):
        self.assertEqual(
            self._dias(
                [(date(2026, 10, 1), date(2026, 12, 31))],
                data_demissao=date(2026, 11, 10),
            ),
            0,
        )


class TestSalarioProporcional(PayrollCommon):
    """Holerite de 10/2026 com contrato iniciado, encerrado ou afastado no mês."""

    def _holerite(self, wage, date_start, date_end=None, **extra):
        emp = self._create_employee()
        contract = self._create_contract(emp, wage=wage, date_start=date_start)
        if date_end:
            contract.date_end = date_end
        if extra.get("periculosidade"):
            contract.l10n_br_periculosidade = True
        return emp, contract, self._create_payslip(emp, contract, OUT_INI, OUT_FIM)

    def test_admissao_no_meio_do_mes(self):
        _emp, _c, slip = self._holerite(6000.0, date(2026, 10, 15))
        self.assertAlmostEqualMoney(self._get_line_total(slip, "SALARIO_BASE"), 3400.0)
        self.assertAlmostEqualMoney(self._get_line_total(slip, "GROSS"), 3400.0)

    def test_desligamento_no_meio_do_mes(self):
        _emp, _c, slip = self._holerite(5000.0, date(2023, 1, 2), date(2026, 10, 20))
        self.assertAlmostEqualMoney(self._get_line_total(slip, "SALARIO_BASE"), 3333.33)

    def test_mes_cheio_inalterado(self):
        _emp, _c, slip = self._holerite(5000.0, date(2023, 1, 2))
        self.assertAlmostEqualMoney(self._get_line_total(slip, "SALARIO_BASE"), 5000.0)

    def test_periculosidade_acompanha_os_dias(self):
        _emp, _c, slip = self._holerite(6000.0, date(2026, 10, 15), periculosidade=True)
        self.assertAlmostEqualMoney(
            self._get_line_total(slip, "ADICIONAL_PERICULOSIDADE"), 1020.0
        )

    def test_insalubridade_acompanha_os_dias(self):
        emp = self._create_employee()
        contract = self._create_contract(
            emp, wage=6000.0, date_start=date(2026, 10, 15)
        )
        contract.write(
            {"l10n_br_insalubridade": True, "l10n_br_grau_insalubridade": "minimo"}
        )
        slip = self._create_payslip(emp, contract, OUT_INI, OUT_FIM)
        sm = slip._get_tools_dict()["br"].salario_minimo()
        self.assertAlmostEqualMoney(
            self._get_line_total(slip, "ADICIONAL_INSALUBRIDADE"),
            round(sm * 0.10 * 17 / 30, 2),
        )

    def test_afastamento_por_doenca_acima_de_15_dias(self):
        tipo = self.env["hr.leave.type"].create(
            {
                "name": "Afastamento por doença (teste)",
                "requires_allocation": "no",
                "leave_validation_type": "no_validation",
                "l10n_br_afastamento_inss": True,
            }
        )
        emp = self._create_employee()
        contract = self._create_contract(emp, wage=5500.0, date_start=date(2022, 8, 1))
        leave = self.env["hr.leave"].create(
            {
                "employee_id": emp.id,
                "holiday_status_id": tipo.id,
                "request_date_from": date(2026, 10, 5),
                "request_date_to": date(2026, 10, 26),
            }
        )
        if leave.state != "validate":
            leave.sudo().action_validate()
        slip = self._create_payslip(emp, contract, OUT_INI, OUT_FIM)
        self.assertAlmostEqualMoney(self._get_line_total(slip, "SALARIO_BASE"), 4216.67)


class TestMigracaoFormulas(PayrollCommon):
    """A migração troca só as fórmulas padrão antigas (regras são noupdate)."""

    def _migrar(self):
        caminho = Path(__file__).parent.parent / "migrations/18.0.1.1.0"
        spec = importlib.util.spec_from_file_location(
            "post_migration_tg82", caminho / "post-migration.py"
        )
        modulo = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(modulo)
        modulo.migrate(self.env.cr, "18.0.1.0.0")
        return modulo

    def test_formula_padrao_antiga_e_atualizada(self):
        modulo = self._migrar()
        regras = {
            xmlid: self.env.ref(f"l10n_br_hr_payroll.{xmlid}")
            for xmlid in modulo.FORMULAS_ANTIGAS
        }
        novas = {x: r.amount_python_compute for x, r in regras.items()}
        for xmlid, regra in regras.items():
            regra.amount_python_compute = modulo.FORMULAS_ANTIGAS[xmlid]
        self._migrar()
        for xmlid, regra in regras.items():
            self.assertEqual(regra.amount_python_compute, novas[xmlid], xmlid)
            self.assertIn("dias_salario", regra.amount_python_compute, xmlid)

    def test_formula_personalizada_e_preservada(self):
        regra = self.env.ref("l10n_br_hr_payroll.hr_rule_salario_base")
        regra.amount_python_compute = "result = contract.wage * 0.9"
        self._migrar()
        self.assertEqual(regra.amount_python_compute, "result = contract.wage * 0.9")


class TestMigracaoInssFerias(PayrollCommon):
    """A migração 18.0.1.2.0 troca só a fórmula padrão antiga do INSS."""

    def _migrar(self):
        caminho = Path(__file__).parent.parent / "migrations/18.0.1.2.0"
        spec = importlib.util.spec_from_file_location(
            "post_migration_tg83", caminho / "post-migration.py"
        )
        modulo = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(modulo)
        modulo.migrate(self.env.cr, "18.0.1.1.0")
        return modulo

    def test_formula_padrao_antiga_e_atualizada(self):
        regra = self.env.ref("l10n_br_hr_payroll.hr_rule_inss")
        nova = regra.amount_python_compute
        regra.amount_python_compute = self._migrar().FORMULA_ANTIGA
        self._migrar()
        self.assertEqual(regra.amount_python_compute, nova)
        self.assertIn("inss_ferias_competencia", nova)

    def test_formula_personalizada_e_preservada(self):
        regra = self.env.ref("l10n_br_hr_payroll.hr_rule_inss")
        regra.amount_python_compute = "result = 1.0"
        self._migrar()
        self.assertEqual(regra.amount_python_compute, "result = 1.0")
