# Copyright 2026 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""Contagem dos dias de salário por empresa: corridos ou mês comercial (TG-171).

Caso real: folha de 10/2026, admitido no dia 14 paga 17 dias no Alterdata
(30 − 14 + 1) e 18 nos dias corridos.
"""
from datetime import date

from odoo.tests.common import BaseCase

from ..models.salary_rules_br import dias_maternidade_mes, dias_salario_mes
from .common import PayrollCommon

COM = "comercial"
COR = "corridos"


def _mes(ano, mes, ultimo):
    return date(ano, mes, 1), date(ano, mes, ultimo)


MESES = {
    "31": _mes(2026, 10, 31),
    "30": _mes(2026, 9, 30),
    "fev28": _mes(2026, 2, 28),
    "fev29": _mes(2028, 2, 29),
}


class TestDiasSalarioComercial(BaseCase):
    def _d(self, mes, modo, **kw):
        ini, fim = MESES[mes]
        return dias_salario_mes(ini, fim, modo=modo, **kw)

    def test_mes_inteiro_paga_30_nos_dois_modos(self):
        for mes in MESES:
            for modo in (COR, COM):
                self.assertEqual(self._d(mes, modo), 30, (mes, modo))

    def test_padrao_e_corridos(self):
        ini, fim = MESES["31"]
        self.assertEqual(dias_salario_mes(ini, fim, date(2026, 10, 14)), 18)

    def test_admissao_mes_de_31(self):
        for dia, com, cor in ((1, 30, 30), (14, 17, 18), (26, 5, 6), (29, 2, 3)):
            adm = date(2026, 10, dia)
            self.assertEqual(self._d("31", COM, data_admissao=adm), com, dia)
            self.assertEqual(self._d("31", COR, data_admissao=adm), cor, dia)

    def test_admissao_dia_31_paga_um_dia(self):
        adm = date(2026, 10, 31)
        self.assertEqual(self._d("31", COM, data_admissao=adm), 1)
        self.assertEqual(self._d("31", COR, data_admissao=adm), 1)

    def test_admissao_mes_de_30(self):
        adm = date(2026, 9, 14)
        self.assertEqual(self._d("30", COM, data_admissao=adm), 17)
        self.assertEqual(self._d("30", COR, data_admissao=adm), 17)

    def test_admissao_em_fevereiro(self):
        adm = date(2026, 2, 15)
        self.assertEqual(self._d("fev28", COM, data_admissao=adm), 16)
        self.assertEqual(self._d("fev28", COR, data_admissao=adm), 14)
        adm = date(2028, 2, 15)
        self.assertEqual(self._d("fev29", COM, data_admissao=adm), 16)
        self.assertEqual(self._d("fev29", COR, data_admissao=adm), 15)

    def test_admissao_no_ultimo_dia_de_fevereiro(self):
        self.assertEqual(self._d("fev28", COM, data_admissao=date(2026, 2, 28)), 3)
        self.assertEqual(self._d("fev29", COM, data_admissao=date(2028, 2, 29)), 2)

    def test_desligamento_mes_de_31(self):
        for dia, com, cor in ((14, 14, 14), (30, 30, 30), (31, 30, 30)):
            dem = date(2026, 10, dia)
            self.assertEqual(self._d("31", COM, data_demissao=dem), com, dia)
            self.assertEqual(self._d("31", COR, data_demissao=dem), cor, dia)

    def test_desligamento_no_ultimo_dia_paga_30_em_fevereiro(self):
        self.assertEqual(self._d("fev28", COM, data_demissao=date(2026, 2, 28)), 30)
        self.assertEqual(self._d("fev29", COM, data_demissao=date(2028, 2, 29)), 30)
        self.assertEqual(self._d("fev28", COR, data_demissao=date(2026, 2, 28)), 30)

    def test_desligamento_meio_de_fevereiro(self):
        dem = date(2026, 2, 14)
        self.assertEqual(self._d("fev28", COM, data_demissao=dem), 14)
        self.assertEqual(self._d("fev28", COR, data_demissao=dem), 14)

    def test_admissao_e_desligamento_no_mesmo_mes(self):
        kw = {"data_admissao": date(2026, 10, 10), "data_demissao": date(2026, 10, 20)}
        self.assertEqual(self._d("31", COM, **kw), 11)
        self.assertEqual(self._d("31", COR, **kw), 11)
        kw = {"data_admissao": date(2026, 10, 10), "data_demissao": date(2026, 10, 31)}
        self.assertEqual(self._d("31", COM, **kw), 21)
        self.assertEqual(self._d("31", COR, **kw), 22)

    def test_admissao_e_desligamento_em_fevereiro(self):
        kw = {"data_admissao": date(2026, 2, 10), "data_demissao": date(2026, 2, 28)}
        self.assertEqual(self._d("fev28", COM, **kw), 21)
        self.assertEqual(self._d("fev28", COR, **kw), 19)

    def test_contrato_fora_do_periodo(self):
        ini, fim = MESES["31"]
        self.assertEqual(dias_salario_mes(ini, fim, date(2026, 11, 1), modo=COM), 0)

    def test_afastamento_previdenciario_em_mes_parcial(self):
        # Admitido 11/10 (comercial 20 dias); afastado 15/10 a 31/10: 15 da empresa
        # (15 a 29) e dos dias 30 e 31 do INSS; só o 31 e o 30 saem.
        af = [(date(2026, 10, 15), date(2026, 10, 31))]
        kw = {"data_admissao": date(2026, 10, 11), "afastamentos_inss": af}
        self.assertEqual(self._d("31", COM, **kw), 19)
        self.assertEqual(self._d("31", COR, **kw), 19)

    def test_afastamento_previdenciario_em_mes_de_31_com_admissao(self):
        # Admitido 02/10, afastado 05/10 a 31/10: INSS de 20 a 31/10 (12 dias
        # civis, 11 comerciais: 20..30).
        af = [(date(2026, 10, 5), date(2026, 10, 31))]
        kw = {"data_admissao": date(2026, 10, 2), "afastamentos_inss": af}
        self.assertEqual(self._d("31", COM, **kw), 29 - 11)
        self.assertEqual(self._d("31", COR, **kw), 30 - 12)

    def test_afastamento_em_mes_inteiro_nao_muda_entre_modos(self):
        af = [(date(2026, 10, 5), date(2026, 10, 26))]
        self.assertEqual(self._d("31", COM, afastamentos_inss=af), 23)
        self.assertEqual(self._d("31", COR, afastamentos_inss=af), 23)

    def test_ferias_em_mes_parcial(self):
        # Admitido 14/10 (17 dias comerciais), férias de 20 a 25/10 (6 dias).
        kw = {
            "data_admissao": date(2026, 10, 14),
            "ferias_gozadas": [(date(2026, 10, 20), date(2026, 10, 25))],
        }
        self.assertEqual(self._d("31", COM, **kw), 11)
        self.assertEqual(self._d("31", COR, **kw), 12)

    def test_ferias_ate_o_fim_do_mes_com_dia_31(self):
        # Férias de 25 a 31/10 com admissão em 14/10: trabalhou 14..24 (11 dias).
        kw = {
            "data_admissao": date(2026, 10, 14),
            "ferias_gozadas": [(date(2026, 10, 25), date(2026, 10, 31))],
        }
        self.assertEqual(self._d("31", COM, **kw), 11)

    def test_so_o_dia_31_de_ferias_nao_tira_o_dia_30_trabalhado(self):
        kw = {
            "data_admissao": date(2026, 10, 14),
            "ferias_gozadas": [(date(2026, 10, 31), date(2026, 10, 31))],
        }
        self.assertEqual(self._d("31", COM, **kw), 17)

    def test_periodo_de_mais_de_um_mes_nao_muda(self):
        ini, fim = date(2026, 9, 16), date(2026, 10, 31)
        adm = date(2026, 9, 20)
        self.assertEqual(
            dias_salario_mes(ini, fim, adm, modo=COM),
            dias_salario_mes(ini, fim, adm, modo=COR),
        )

    def test_maternidade_fecha_com_salario_nos_dois_modos(self):
        lic = [(date(2026, 10, 1), date(2026, 10, 31))]
        for modo, total in ((COM, 17), (COR, 18)):
            ini, fim = MESES["31"]
            kw = {"data_admissao": date(2026, 10, 14), "modo": modo}
            dias = dias_salario_mes(ini, fim, **kw)
            mat = dias_maternidade_mes(ini, fim, maternidade=lic, **kw)
            self.assertEqual(dias, total)
            self.assertEqual(mat, total)

    def test_maternidade_parcial_nao_passa_dos_dias_de_salario(self):
        ini, fim = MESES["31"]
        lic = [(date(2026, 10, 20), date(2026, 12, 31))]
        kw = {"data_admissao": date(2026, 10, 14), "modo": COM}
        mat = dias_maternidade_mes(ini, fim, maternidade=lic, **kw)
        self.assertEqual(mat, 11)  # dias 20..30 comerciais
        self.assertEqual(dias_salario_mes(ini, fim, **kw) - mat, 6)


class TestContagemDiasHolerite(PayrollCommon):
    def _holerite(self, modo, date_start, date_end=None, wage=6000.0):
        self.env.company.l10n_br_contagem_dias_salario = modo
        emp = self._create_employee()
        contract = self._create_contract(emp, wage=wage, date_start=date_start)
        if date_end:
            contract.date_end = date_end
        return contract, self._create_payslip(
            emp, contract, date(2026, 10, 1), date(2026, 10, 31)
        )

    def test_padrao_da_empresa_e_corridos(self):
        field = self.env["res.company"]._fields["l10n_br_contagem_dias_salario"]
        self.assertEqual(field.default(self.env["res.company"]), "corridos")
        self.assertEqual(self.env.company.l10n_br_contagem_dias_salario, "corridos")

    def test_admissao_dia_14_em_cada_modo(self):
        _c, slip = self._holerite(COR, date(2026, 10, 14))
        self.assertAlmostEqualMoney(self._get_line_total(slip, "SALARIO_BASE"), 3600.0)
        _c, slip = self._holerite(COM, date(2026, 10, 14))
        self.assertAlmostEqualMoney(self._get_line_total(slip, "SALARIO_BASE"), 3400.0)

    def test_periculosidade_acompanha_o_modo(self):
        contract, _slip = self._holerite(COM, date(2026, 10, 14))
        contract.l10n_br_periculosidade = True
        slip = self._create_payslip(
            contract.employee_id, contract, date(2026, 10, 1), date(2026, 10, 31)
        )
        self.assertAlmostEqualMoney(
            self._get_line_total(slip, "ADICIONAL_PERICULOSIDADE"), 1020.0
        )

    def test_desligamento_no_ultimo_dia_paga_mes_inteiro(self):
        _c, slip = self._holerite(COM, date(2023, 1, 2), date(2026, 10, 31))
        self.assertAlmostEqualMoney(self._get_line_total(slip, "SALARIO_BASE"), 6000.0)

    def test_holerite_aberto_recalcula_com_o_parametro(self):
        _c, slip = self._holerite(COR, date(2026, 10, 14))
        self.assertAlmostEqualMoney(self._get_line_total(slip, "SALARIO_BASE"), 3600.0)
        self.env.company.l10n_br_contagem_dias_salario = COM
        slip.compute_sheet()
        self.assertAlmostEqualMoney(self._get_line_total(slip, "SALARIO_BASE"), 3400.0)

    def test_holerite_confirmado_nao_muda(self):
        _c, slip = self._holerite(COR, date(2026, 10, 14))
        slip.action_payslip_done()
        self.env.company.l10n_br_contagem_dias_salario = COM
        self.assertEqual(slip.state, "done")
        self.assertAlmostEqualMoney(self._get_line_total(slip, "SALARIO_BASE"), 3600.0)
