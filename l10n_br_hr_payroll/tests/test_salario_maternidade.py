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
        """Valores: salário base + maternidade = dias de salário, em cada caso.

        Os esperados são contados à mão (mês comercial), não calculados pela
        própria função: (período, licença, admissão, dias de salário, maternidade).
        """
        casos = [
            # admitida 08/10 (24 dias); licença 03 a 19/10: só 08 a 19 = 12 dias
            (OUT_INI, OUT_FIM, (date(2026, 10, 3), date(2026, 10, 19)), 12, 24),
            # licença de 1 dia
            (OUT_INI, OUT_FIM, (date(2026, 10, 20), date(2026, 10, 20)), 1, 24),
            # licença antes da admissão: não conta
            (OUT_INI, OUT_FIM, (date(2026, 10, 1), date(2026, 10, 7)), 0, 24),
            # licença até o fim do mês: admitida 08/10, são 24 dias corridos (08 a 31)
            (OUT_INI, OUT_FIM, (date(2026, 10, 8), date(2026, 10, 31)), 24, 24),
        ]
        for ini, fim, licenca, esperado_mat, esperado_total in casos:
            sal, mat = _mat(*licenca, (ini, fim), data_admissao=date(2026, 10, 8))
            self.assertEqual(mat, esperado_mat, licenca)
            self.assertEqual(sal + mat, esperado_total, licenca)


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


class TestMaternidadeEstruturas(PayrollCommon):
    """Onde o ``SALARIO_BASE`` novo vai, a rubrica vai junto (ou não há desconto)."""

    def _licenca(self, emp):
        tipo = self.env["hr.leave.type"].create(
            {
                "name": "Licença-maternidade (estrutura)",
                "requires_allocation": "no",
                "leave_validation_type": "no_validation",
                "l10n_br_salario_maternidade": True,
            }
        )
        leave = self.env["hr.leave"].create(
            {
                "employee_id": emp.id,
                "holiday_status_id": tipo.id,
                "request_date_from": OUT_INI,
                "request_date_to": OUT_FIM,
            }
        )
        if leave.state != "validate":
            leave.sudo().action_validate()

    def test_estatutario_traz_a_rubrica_junto_do_salario_base(self):
        regra = self.env.ref("l10n_br_hr_payroll.hr_rule_salario_maternidade")
        self.assertIn(regra, self.structure_estatuto.rule_ids)
        emp = self._create_employee()
        contract = self._create_contract(
            emp, wage=4000.0, structure=self.structure_estatuto
        )
        self._licenca(emp)
        slip = self._create_payslip(emp, contract, OUT_INI, OUT_FIM)
        self.assertAlmostEqualMoney(
            self._get_line_total(slip, "SALARIO_MATERNIDADE"), 4000.0
        )
        self.assertAlmostEqualMoney(self._get_line_total(slip, "GROSS"), 4000.0)

    def test_estrutura_sem_a_rubrica_paga_o_salario_inteiro_no_base(self):
        """Estrutura de terceiros com SALARIO_BASE e sem a rubrica: não zera."""
        estrutura = self.env["hr.payroll.structure"].create(
            {
                "name": "Estágio (teste)",
                "code": "ESTAGIO_T87",
                "rule_ids": [
                    (
                        6,
                        0,
                        [
                            self.env.ref("l10n_br_hr_payroll.hr_rule_salario_base").id,
                            self.env.ref("l10n_br_hr_payroll.hr_rule_gross").id,
                            self.env.ref("l10n_br_hr_payroll.hr_rule_net").id,
                        ],
                    )
                ],
            }
        )
        emp = self._create_employee()
        contract = self._create_contract(emp, wage=2000.0, structure=estrutura)
        self._licenca(emp)
        slip = self._create_payslip(emp, contract, OUT_INI, OUT_FIM)
        self.assertAlmostEqualMoney(self._get_line_total(slip, "SALARIO_BASE"), 2000.0)
        self.assertAlmostEqualMoney(self._get_line_total(slip, "GROSS"), 2000.0)


class TestMigracaoAtualizacaoDeBanco(PayrollCommon):
    """Banco que já estava instalado: visão órfã e fórmula personalizada."""

    def _carregar(self, nome):
        caminho = file_path(f"l10n_br_hr_payroll/migrations/18.0.1.6.0/{nome}.py")
        spec = importlib.util.spec_from_file_location(f"tg87_{nome}", caminho)
        modulo = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(modulo)
        return modulo

    def test_pre_migracao_remove_a_visao_orfa_e_e_idempotente(self):
        view = self.env["ir.ui.view"].create(
            {
                "name": "orfa esocial",
                "model": "hr.leave.type",
                "type": "form",
                "arch": "<form/>",
            }
        )
        dado = self.env["ir.model.data"].create(
            {
                "module": "l10n_br_esocial",
                "name": "hr_leave_type_view_form_esocial",
                "model": "ir.ui.view",
                "res_id": view.id,
            }
        )
        pre = self._carregar("pre-migration")
        pre.migrate(self.env.cr, "18.0.1.5.0")
        pre.migrate(self.env.cr, "18.0.1.5.0")
        self.env.invalidate_all()
        self.assertFalse(view.exists())
        self.assertFalse(dado.exists())

    def test_formula_personalizada_nao_liga_a_rubrica_nova(self):
        """SALARIO_BASE personalizada + rubrica nova pagaria o salário em dobro."""
        regra_mat = self.env.ref("l10n_br_hr_payroll.hr_rule_salario_maternidade")
        comp = self.env.ref("l10n_br_hr_payroll.hr_rule_comp_salario_maternidade")
        self.structure_clt.write({"rule_ids": [(3, regra_mat.id), (3, comp.id)]})
        self.structure_estatuto.write({"rule_ids": [(3, regra_mat.id)]})
        base = self.env.ref("l10n_br_hr_payroll.hr_rule_salario_base")
        base.amount_python_compute = "# personalizada\nresult = contract.wage"
        self._carregar("post-migration").migrate(self.env.cr, "18.0.1.5.0")
        self.assertNotIn(regra_mat, self.structure_clt.rule_ids)
        self.assertNotIn(regra_mat, self.structure_estatuto.rule_ids)

    def test_formula_padrao_liga_clt_e_estatutario(self):
        regra_mat = self.env.ref("l10n_br_hr_payroll.hr_rule_salario_maternidade")
        self.structure_clt.write({"rule_ids": [(3, regra_mat.id)]})
        self.structure_estatuto.write({"rule_ids": [(3, regra_mat.id)]})
        modulo = self._carregar("post-migration")
        base = self.env.ref("l10n_br_hr_payroll.hr_rule_salario_base")
        base.amount_python_compute = modulo.FORMULAS_ANTIGAS["hr_rule_salario_base"]
        modulo.migrate(self.env.cr, "18.0.1.5.0")
        self.assertIn(regra_mat, self.structure_clt.rule_ids)
        self.assertIn(regra_mat, self.structure_estatuto.rule_ids)
