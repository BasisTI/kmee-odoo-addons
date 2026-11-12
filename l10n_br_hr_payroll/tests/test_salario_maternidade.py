# Copyright 2026 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""TG-87: salário-maternidade com rubrica própria, compensada na guia.

O salário dos dias de licença-maternidade sai de ``SALARIO_BASE`` e vai para
``SALARIO_MATERNIDADE``, a partir do MESMO conjunto de dias da TG-82
(admissão, desligamento, afastamento do INSS, férias).
"""

import importlib.util
from datetime import date

from odoo.tools import file_path

from ..models.salary_rules_br import dias_maternidade_mes, dias_salario_mes
from .common import PayrollCommon

OUT_INI = date(2026, 10, 1)
OUT_FIM = date(2026, 10, 31)


def _mat(inicio, fim, periodo=(OUT_INI, OUT_FIM), **kw):
    """Par ``(dias de salário base, dias de maternidade)`` do período."""
    ini, fi = periodo
    licenca = [(inicio, fim)]
    dias = dias_salario_mes(ini, fi, **kw)
    mat = dias_maternidade_mes(ini, fi, maternidade=licenca, **kw)
    return dias - mat, mat


class TestDiasMaternidade(PayrollCommon):
    """Função pura: os dias de maternidade e os de salário fecham sempre."""

    def test_sem_licenca_nao_ha_maternidade(self):
        self.assertEqual(dias_maternidade_mes(OUT_INI, OUT_FIM), 0)

    def test_mes_inteiro_de_licenca_paga_30_dias(self):
        self.assertEqual(_mat(OUT_INI, OUT_FIM), (0, 30))
        self.assertEqual(
            _mat(
                date(2026, 2, 1),
                date(2026, 2, 28),
                (date(2026, 2, 1), date(2026, 2, 28)),
            ),
            (0, 30),
        )

    def test_licenca_parcial_divide_os_30_dias(self):
        self.assertEqual(_mat(date(2026, 10, 21), date(2026, 10, 30)), (20, 10))

    def test_licenca_que_comecou_antes_e_termina_no_mes(self):
        self.assertEqual(_mat(date(2026, 9, 10), date(2026, 10, 10)), (20, 10))

    def test_admissao_no_mes_da_licenca(self):
        """N1: admitida 16/10, licença 16 a 31/10: tudo é maternidade (16 dias)."""
        self.assertEqual(
            _mat(
                date(2026, 10, 16), date(2026, 10, 31), data_admissao=date(2026, 10, 16)
            ),
            (0, 16),
        )

    def test_desligamento_no_mes_da_licenca(self):
        """N1: desligada 15/10, licença de 01 a 15/10: 15 dias de maternidade."""
        self.assertEqual(
            _mat(OUT_INI, date(2026, 10, 15), data_demissao=date(2026, 10, 15)),
            (0, 15),
        )

    def test_licenca_antes_da_admissao_nao_conta(self):
        """Licença de 01 a 20/10, admitida 16/10: só 16 a 20 (5 dias) contam."""
        self.assertEqual(
            _mat(OUT_INI, date(2026, 10, 20), data_admissao=date(2026, 10, 16)),
            (11, 5),
        )

    def test_afastamento_do_inss_no_mes_da_licenca(self):
        """N1: INSS de 01 a 20/10 (15 da empresa) e maternidade de 21 a 31/10.

        A empresa paga 01 a 15; 16 a 20 são do INSS (5 dias fora, 25 de salário);
        21 a 31 são maternidade, 10 dias comerciais (o dia 31 não conta no mês
        de 30). Soma: 15 de salário base + 10 de maternidade = 25.
        """
        self.assertEqual(
            _mat(
                date(2026, 10, 21),
                OUT_FIM,
                afastamentos_inss=[(OUT_INI, date(2026, 10, 20))],
            ),
            (15, 10),
        )

    def test_ferias_ja_pagas_nao_viram_maternidade(self):
        self.assertEqual(
            _mat(
                OUT_INI,
                OUT_FIM,
                ferias_gozadas=[(date(2026, 10, 1), date(2026, 10, 10))],
            ),
            (0, 20),
        )

    def test_periodo_maior_que_30_dias_usa_a_proporcao_do_periodo(self):
        """N2: 16/09 a 31/10 (46 dias) paga 30; licença de 31 dias em outubro."""
        ini, fim = date(2026, 9, 16), OUT_FIM
        licenca = [(OUT_INI, OUT_FIM)]
        dias = dias_salario_mes(ini, fim)
        mat = dias_maternidade_mes(ini, fim, maternidade=licenca)
        self.assertEqual(dias, 30)
        self.assertEqual(mat, 20)  # 30 x 31/46 = 20,2

    def test_periodo_anual_com_licenca_em_um_mes(self):
        ini, fim = date(2026, 1, 1), date(2026, 12, 31)
        mat = dias_maternidade_mes(ini, fim, maternidade=[(OUT_INI, OUT_FIM)])
        self.assertEqual(mat, 3)  # 30 x 31/365 = 2,5: o meio-dia sobe

    def test_periodo_maior_que_30_dias_sem_licenca(self):
        self.assertEqual(
            dias_maternidade_mes(date(2026, 9, 16), OUT_FIM, maternidade=[]), 0
        )

    def test_a_soma_fecha_nos_dias_de_salario(self):
        for ini, fim in (
            (date(2026, 10, 3), date(2026, 10, 19)),
            (date(2026, 9, 20), date(2026, 11, 5)),
            (date(2026, 10, 31), date(2026, 10, 31)),
        ):
            sal, mat = _mat(ini, fim, data_admissao=date(2026, 10, 8))
            self.assertGreaterEqual(sal, 0)
            self.assertGreaterEqual(mat, 0)
            self.assertEqual(
                sal + mat, dias_salario_mes(OUT_INI, OUT_FIM, date(2026, 10, 8))
            )


class TestHoleriteMaternidade(PayrollCommon):
    """Holerite calculado: rubrica própria, bases, guia e parâmetro patronal."""

    def _tipo(self, maternidade=True):
        return self.env["hr.leave.type"].create(
            {
                "name": "Licença-maternidade (teste)",
                "requires_allocation": "no",
                "leave_validation_type": "no_validation",
                "l10n_br_salario_maternidade": maternidade,
            }
        )

    def _licenca(self, emp, inicio, fim, maternidade=True):
        leave = self.env["hr.leave"].create(
            {
                "employee_id": emp.id,
                "holiday_status_id": self._tipo(maternidade).id,
                "request_date_from": inicio,
                "request_date_to": fim,
            }
        )
        if leave.state != "validate":
            leave.sudo().action_validate()
        return leave

    def _holerite(self, wage=6500.0, inicio=OUT_INI, fim=OUT_FIM, **contrato):
        emp = self._create_employee()
        contract = self._create_contract(emp, wage=wage, **contrato)
        return emp, contract

    def test_mes_inteiro_de_licenca_vai_na_rubrica_propria(self):
        emp, contract = self._holerite()
        self._licenca(emp, OUT_INI, OUT_FIM)
        slip = self._create_payslip(emp, contract, OUT_INI, OUT_FIM)
        self.assertAlmostEqualMoney(
            self._get_line_total(slip, "SALARIO_MATERNIDADE"), 6500.0
        )
        self.assertFalse(self._get_line_total(slip, "SALARIO_BASE"))
        self.assertAlmostEqualMoney(self._get_line_total(slip, "GROSS"), 6500.0)

    def test_sem_licenca_nao_ha_rubrica(self):
        emp, contract = self._holerite()
        slip = self._create_payslip(emp, contract, OUT_INI, OUT_FIM)
        self.assertFalse(
            slip.line_ids.filtered(lambda ln: ln.code == "SALARIO_MATERNIDADE")
        )
        self.assertFalse(
            slip.line_ids.filtered(lambda ln: ln.code == "COMP_SALARIO_MATERNIDADE")
        )
        self.assertAlmostEqualMoney(self._get_line_total(slip, "SALARIO_BASE"), 6500.0)

    def test_licenca_parcial_divide_o_salario_sem_sobra(self):
        emp, contract = self._holerite(wage=3000.0)
        self._licenca(emp, date(2026, 10, 21), date(2026, 10, 30))
        slip = self._create_payslip(emp, contract, OUT_INI, OUT_FIM)
        self.assertAlmostEqualMoney(
            self._get_line_total(slip, "SALARIO_MATERNIDADE"), 1000.0
        )
        self.assertAlmostEqualMoney(self._get_line_total(slip, "SALARIO_BASE"), 2000.0)

    def test_admissao_no_mes_da_licenca_paga_o_salario_proporcional_todo(self):
        """N1: o salário já proporcionalizado inteiro é maternidade (16 dias)."""
        emp, contract = self._holerite(wage=6500.0, date_start=date(2026, 10, 16))
        self._licenca(emp, date(2026, 10, 16), OUT_FIM)
        slip = self._create_payslip(emp, contract, OUT_INI, OUT_FIM)
        self.assertAlmostEqualMoney(
            self._get_line_total(slip, "SALARIO_MATERNIDADE"), round(6500 * 16 / 30, 2)
        )
        self.assertFalse(self._get_line_total(slip, "SALARIO_BASE"))

    def test_licenca_de_tipo_nao_marcado_e_salario_comum(self):
        emp, contract = self._holerite()
        self._licenca(emp, OUT_INI, OUT_FIM, maternidade=False)
        slip = self._create_payslip(emp, contract, OUT_INI, OUT_FIM)
        self.assertFalse(self._get_line_total(slip, "SALARIO_MATERNIDADE"))
        self.assertAlmostEqualMoney(self._get_line_total(slip, "SALARIO_BASE"), 6500.0)

    def test_licenca_nao_aprovada_nao_conta(self):
        emp, contract = self._holerite()
        leave = self._licenca(emp, OUT_INI, OUT_FIM)
        leave.sudo().action_refuse()
        slip = self._create_payslip(emp, contract, OUT_INI, OUT_FIM)
        self.assertFalse(self._get_line_total(slip, "SALARIO_MATERNIDADE"))

    def test_entra_nas_bases_de_inss_irrf_e_fgts(self):
        """Mesmos valores do salário comum: só a rubrica muda."""
        emp, contract = self._holerite()
        comum = self._create_payslip(emp, contract, OUT_INI, OUT_FIM)
        self._licenca(emp, OUT_INI, OUT_FIM)
        slip = self._create_payslip(emp, contract, OUT_INI, OUT_FIM)
        for codigo in ("INSS", "IRRF", "FGTS", "NET"):
            self.assertAlmostEqualMoney(
                self._get_line_total(slip, codigo),
                self._get_line_total(comum, codigo),
                codigo,
            )

    def test_compensacao_na_guia_e_informativa(self):
        emp, contract = self._holerite()
        self._licenca(emp, OUT_INI, OUT_FIM)
        slip = self._create_payslip(emp, contract, OUT_INI, OUT_FIM)
        linha = slip.line_ids.filtered(lambda ln: ln.code == "COMP_SALARIO_MATERNIDADE")
        self.assertEqual(linha.category_id.code, "INFO")
        self.assertAlmostEqualMoney(linha.total, 6500.0)
        # Informativa: não muda o líquido (= bruto - INSS - IRRF).
        liquido = (
            self._get_line_total(slip, "GROSS")
            - self._get_line_total(slip, "INSS")
            - self._get_line_total(slip, "IRRF")
        )
        self.assertAlmostEqualMoney(self._get_line_total(slip, "NET"), liquido)

    def test_patronal_incide_por_padrao_como_antes(self):
        emp, contract = self._holerite()
        comum = self._create_payslip(emp, contract, OUT_INI, OUT_FIM)
        self._licenca(emp, OUT_INI, OUT_FIM)
        slip = self._create_payslip(emp, contract, OUT_INI, OUT_FIM)
        self.assertTrue(self.env.company.l10n_br_hr_patronal_sobre_salario_maternidade)
        for codigo in ("CPP", "RAT", "TERCEIROS"):
            self.assertAlmostEqualMoney(
                self._get_line_total(slip, codigo),
                self._get_line_total(comum, codigo),
                codigo,
            )

    def test_parametro_da_empresa_tira_cpp_e_rat_e_mantem_terceiros(self):
        emp, contract = self._holerite()
        self._licenca(emp, OUT_INI, OUT_FIM)
        padrao = self._create_payslip(emp, contract, OUT_INI, OUT_FIM)
        self.env.company.l10n_br_hr_patronal_sobre_salario_maternidade = False
        slip = self._create_payslip(emp, contract, OUT_INI, OUT_FIM)
        self.assertFalse(self._get_line_total(slip, "CPP"))
        self.assertFalse(self._get_line_total(slip, "RAT"))
        self.assertAlmostEqualMoney(
            self._get_line_total(slip, "TERCEIROS"),
            self._get_line_total(padrao, "TERCEIROS"),
        )

    def test_parametro_so_tira_a_parte_da_maternidade(self):
        emp, contract = self._holerite(wage=3000.0)
        self._licenca(emp, date(2026, 10, 21), date(2026, 10, 30))
        self.env.company.l10n_br_hr_patronal_sobre_salario_maternidade = False
        slip = self._create_payslip(emp, contract, OUT_INI, OUT_FIM)
        aliquota = slip._get_tools_dict()["br"].aliquotas_patronais(contract)
        self.assertAlmostEqualMoney(
            self._get_line_total(slip, "CPP"), round(2000.0 * aliquota.cpp, 2)
        )


class TestMigracaoMaternidade(PayrollCommon):
    """A migração 18.0.1.6.0 troca só as fórmulas padrão antigas, sem repetir."""

    def _migrar(self):
        caminho = file_path(
            "l10n_br_hr_payroll/migrations/18.0.1.6.0/post-migration.py"
        )
        spec = importlib.util.spec_from_file_location("post_migration_tg87", caminho)
        modulo = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(modulo)
        modulo.migrate(self.env.cr, "18.0.1.5.0")
        return modulo

    def test_formulas_antigas_sao_atualizadas(self):
        modulo = self._migrar()
        regras = {
            x: self.env.ref(f"l10n_br_hr_payroll.{x}") for x in modulo.FORMULAS_ANTIGAS
        }
        novas = {x: r.amount_python_compute for x, r in regras.items()}
        for xmlid, regra in regras.items():
            regra.amount_python_compute = modulo.FORMULAS_ANTIGAS[xmlid]
        self._migrar()
        for xmlid, regra in regras.items():
            self.assertEqual(regra.amount_python_compute, novas[xmlid], xmlid)
        self.assertIn(
            "dias_maternidade",
            regras["hr_rule_salario_base"].amount_python_compute,
        )

    def test_formula_personalizada_e_preservada(self):
        regra = self.env.ref("l10n_br_hr_payroll.hr_rule_cpp_patronal")
        regra.amount_python_compute = "result = 0.0"
        self._migrar()
        self.assertEqual(regra.amount_python_compute, "result = 0.0")

    def test_liga_as_rubricas_a_estrutura_uma_vez(self):
        regras = self.env.ref("l10n_br_hr_payroll.hr_rule_salario_maternidade")
        regras |= self.env.ref("l10n_br_hr_payroll.hr_rule_comp_salario_maternidade")
        self.structure_clt.write({"rule_ids": [(3, r.id) for r in regras]})
        self._migrar()
        self._migrar()
        codigos = self.structure_clt.rule_ids.mapped("code")
        self.assertEqual(codigos.count("SALARIO_MATERNIDADE"), 1)
        self.assertEqual(codigos.count("COMP_SALARIO_MATERNIDADE"), 1)
