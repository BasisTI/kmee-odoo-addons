# Copyright 2026 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""TG-152: férias que atravessam o mês no S-1200, rateadas por dias de gozo.

MOS do eSocial S-1.3, S-1010, item 23 (pp. 112-114), exemplo (c): gozo de
10/11 a 10/12 vai ao S-1200 de cada competência, rateado por dias. O exemplo diz
"20 + 10"; a contagem de dias corridos inclusiva dá 21 + 10 (o MOS é impreciso).
"""

import importlib.util
from pathlib import Path

from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase
from odoo.tools import mute_logger


class TestS1200FeriasRateio(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        mute = mute_logger(
            "odoo.addons.l10n_br_esocial.models.intermediarios.base_intermediario",
            "odoo.addons.l10n_br_esocial.models.esocial_lote",
        )
        mute.__enter__()
        cls.addClassCleanup(mute.__exit__, None, None, None)
        cls.company = cls.env.company
        if not cls.company.partner_id.vat:
            cls.company.partner_id.write({"vat": "02.546.716/0001-46"})
        cls.company.l10n_br_esocial_cod_lotacao = "LOT001"
        cat = cls.env.ref("l10n_br_esocial.cat_trab_101")
        cls.employee = cls.env["hr.employee"].create(
            {
                "name": "Rateio Férias",
                "cnpj_cpf": "076.166.929-41",
                "l10n_br_esocial_matricula": "MAT152",
                "l10n_br_esocial_categoria_id": cat.id,
            }
        )
        cls.contract = cls.env["hr.contract"].create(
            {
                "name": "Contrato rateio",
                "employee_id": cls.employee.id,
                "wage": 3000.0,
                "date_start": "2024-01-02",
                "state": "open",
            }
        )
        cls.rule = cls.env["hr.salary.rule"].search(
            [("code", "=", "SALARIO_BASE")], limit=1
        ) or cls.env["hr.salary.rule"].search([], limit=1)
        cls.rule.write(
            {
                "l10n_br_esocial_cod_rubr": "SAL_BASE",
                "l10n_br_esocial_ide_tab_rubr": "1",
                "l10n_br_esocial_nat_rubr_id": cls.env.ref(
                    "l10n_br_esocial.nat_rubr_1000"
                ).id,
                "l10n_br_esocial_tp_rubr": "1",
                "l10n_br_esocial_cod_inc_cp": "11",
                "l10n_br_esocial_cod_inc_irrf": "11",
                "l10n_br_esocial_cod_inc_fgts": "11",
            }
        )
        cls.rule_inss = cls._regra_extra(
            "INSS_T152", "INSS_F", "9201", "2", "31", "41", "00"
        )
        cls.rule_irrf = cls._regra_extra(
            "IRRF_T152", "IRRF_F", "9203", "2", "00", "33", "00"
        )
        cls.rule_ferias = cls._regra_extra(
            "FERIAS_T152", "FERIAS_F", "1016", "1", "11", "13", "11"
        )
        cls.rule_abono = cls._regra_extra(
            "ABONO_PECUNIARIO", "ABONO_F", "1023", "1", "00", "75", "00"
        )
        cls.rule_pensao = cls._regra_extra(
            "PENSAO_T152", "PENSAO_F", "9213", "2", "00", "53", "00"
        )
        cls.estrutura = cls.env["hr.payroll.structure"].search(
            [("code", "=", "FERIAS")], limit=1
        ) or cls.env["hr.payroll.structure"].create(
            {"name": "Férias (teste)", "code": "FERIAS"}
        )

    @classmethod
    def _regra_extra(cls, code, cod_rubr, natureza, tp, cp, irrf, fgts):
        return cls.env["hr.salary.rule"].create(
            {
                "name": code,
                "code": code,
                "sequence": 5,
                "category_id": cls.rule.category_id.id,
                "l10n_br_esocial_cod_rubr": cod_rubr,
                "l10n_br_esocial_ide_tab_rubr": "BASIS",
                "l10n_br_esocial_nat_rubr_id": cls.env.ref(
                    "l10n_br_esocial.nat_rubr_%s" % natureza
                ).id,
                "l10n_br_esocial_tp_rubr": tp,
                "l10n_br_esocial_cod_inc_cp": cp,
                "l10n_br_esocial_cod_inc_irrf": irrf,
                "l10n_br_esocial_cod_inc_fgts": fgts,
            }
        )

    def _recibo(self, de, ate, valores, codigos=None, regras=None):
        slip = self.env["hr.payslip"].create(
            {
                "name": "Recibo de férias",
                "employee_id": self.employee.id,
                "contract_id": self.contract.id,
                "struct_id": self.estrutura.id,
                "date_from": de,
                "date_to": ate,
            }
        )
        for i, valor in enumerate(valores):
            self.env["hr.payslip.line"].create(
                {
                    "slip_id": slip.id,
                    "salary_rule_id": (regras or {}).get(i, self.rule).id,
                    "name": "Linha %d" % i,
                    "code": (codigos or {}).get(i, "L%d" % i),
                    "employee_id": self.employee.id,
                    "contract_id": self.contract.id,
                    "quantity": 1,
                    "amount": valor,
                    "rate": 100,
                }
            )
        return slip

    def _s1200(self, slip, per_apur):
        return self.env["l10n_br.esocial.s1200"].create(
            {
                "employee_id": self.employee.id,
                "payslip_ids": [(6, 0, slip.ids)],
                "per_apur": per_apur,
                "ind_apuracao": "1",
                "company_id": self.company.id,
            }
        )

    def _soma(self, s1200):
        return sum(float(i["vr_rubr"]) for i in s1200._build_itens_remun())

    def test_competencias_exemplo_c_do_mos(self):
        """Gozo de 10/11 a 10/12: 21 dias em novembro, 10 em dezembro."""
        slip = self._recibo("2026-11-10", "2026-12-10", [])
        self.assertEqual(
            slip._l10n_br_competencias_ferias(), [("2026-11", 21), ("2026-12", 10)]
        )

    def test_recibo_no_mes_e_uma_competencia_so(self):
        slip = self._recibo("2026-11-02", "2026-11-21", [1000.0])
        self.assertEqual(slip._l10n_br_competencias_ferias(), [("2026-11", 20)])
        self.assertEqual(self._soma(self._s1200(slip, "2026-11")), 1000.0)

    def test_mensal_nao_e_rateado(self):
        slip = self._recibo("2026-11-10", "2026-12-10", [1000.0])
        slip.struct_id = self.env["hr.payroll.structure"].create(
            {"name": "Mensal (teste)", "code": "MENSAL_T152"}
        )
        self.assertEqual(slip._l10n_br_competencias_ferias(), [("2026-11", 0)])
        self.assertEqual(self._soma(self._s1200(slip, "2026-11")), 1000.0)

    def test_s1200_de_cada_competencia_rateado_por_dias(self):
        # 31 dias: 21 em novembro, 10 em dezembro.
        slip = self._recibo("2026-11-10", "2026-12-10", [3100.0])
        nov = self._soma(self._s1200(slip, "2026-11"))
        dez = self._soma(self._s1200(slip, "2026-12"))
        self.assertEqual(nov, 2100.0)
        self.assertEqual(dez, 1000.0)

    def test_soma_das_partes_bate_com_o_recibo_ao_centavo(self):
        """Resíduo do arredondamento na última parte, com valores que não dividem."""
        for total in (1234.57, 0.05, 999.99, 3333.33, 10000.01):
            slip = self._recibo("2026-11-10", "2026-12-10", [total])
            nov = self._soma(self._s1200(slip, "2026-11"))
            dez = self._soma(self._s1200(slip, "2026-12"))
            self.assertAlmostEqual(nov + dez, total, places=2, msg=str(total))
            self.assertEqual(nov, round(total * 21 / 31, 2))

    def test_tres_competencias_residuo_na_ultima(self):
        # 20/10 a 05/12: 12 + 30 + 5 = 47 dias.
        slip = self._recibo("2026-10-20", "2026-12-05", [1000.01])
        partes = [
            self._soma(self._s1200(slip, p)) for p in ("2026-10", "2026-11", "2026-12")
        ]
        self.assertAlmostEqual(sum(partes), 1000.01, places=2)
        self.assertEqual(partes[0], round(1000.01 * 12 / 47, 2))
        self.assertEqual(partes[1], round(1000.01 * 30 / 47, 2))

    def test_abono_e_terco_rateados_na_proporcao_dos_dias_de_gozo(self):
        """TG-152#P1: abono pecuniário e terço do abono rateiam como as férias."""
        slip = self._recibo(
            "2026-11-10",
            "2026-12-10",
            [3100.0, 620.0, 206.67],
            {1: "ABONO_PECUNIARIO", 2: "ADICIONAL_ABONO"},
        )
        nov = self._soma(self._s1200(slip, "2026-11"))
        dez = self._soma(self._s1200(slip, "2026-12"))
        self.assertEqual(
            nov, 2100.0 + round(620.0 * 21 / 31, 2) + round(206.67 * 21 / 31, 2)
        )
        self.assertAlmostEqual(nov + dez, 3100.0 + 620.0 + 206.67, places=2)

    # ── Adiantamento (MOS S-1010, item 23, pp. 112-114, exemplos a e c) ─────

    def _por_rubrica(self, s1200):
        itens = {}
        for item in s1200._build_itens_remun():
            itens[item["cod_rubr"]] = itens.get(item["cod_rubr"], 0.0) + float(
                item["vr_rubr"]
            )
        return itens

    def _pago(self, slip, data):
        slip.l10n_br_esocial_data_pagamento = data
        return slip

    def test_exemplo_a_pago_no_mes_anterior_ao_gozo(self):
        """Gozo 01/12 a 30/12, pago em 28/11: 1015 em 11; 1016/1017 e 9221 em 12."""
        slip = self._pago(
            self._recibo("2026-12-01", "2026-12-30", [3000.0, 1000.0]), "2026-11-28"
        )
        self.assertEqual(slip._esocial_competencias_s1200(), ["2026-11", "2026-12"])
        nov = self._por_rubrica(self._s1200(slip, "2026-11"))
        dez = self._por_rubrica(self._s1200(slip, "2026-12"))
        self.assertEqual(nov, {"ANTECIPFERI": 4000.0})
        self.assertEqual(dez["DESCANTECIPFERI"], 4000.0)
        self.assertEqual(dez["SAL_BASE"], 4000.0)

    def test_exemplo_b_opcao_2_pago_no_mes_do_gozo_sem_adiantamento(self):
        slip = self._pago(
            self._recibo("2026-11-10", "2026-11-30", [3000.0, 1000.0]), "2026-11-07"
        )
        self.assertEqual(slip._esocial_competencias_s1200(), ["2026-11"])
        nov = self._por_rubrica(self._s1200(slip, "2026-11"))
        self.assertEqual(set(nov), {"SAL_BASE"})

    def test_exemplo_c_opcao_2_gozo_parcial_no_mes_do_pagamento(self):
        """10/11 a 10/12 pago em 07/11: 1015 só da parte de dezembro, em 11."""
        slip = self._pago(
            self._recibo("2026-11-10", "2026-12-10", [3100.0]), "2026-11-07"
        )
        self.assertEqual(slip._esocial_competencias_s1200(), ["2026-11", "2026-12"])
        nov = self._por_rubrica(self._s1200(slip, "2026-11"))
        dez = self._por_rubrica(self._s1200(slip, "2026-12"))
        self.assertEqual(nov["SAL_BASE"], 2100.0)
        self.assertEqual(nov["ANTECIPFERI"], 1000.0)
        self.assertNotIn("DESCANTECIPFERI", nov)
        self.assertEqual(dez["SAL_BASE"], 1000.0)
        self.assertEqual(dez["DESCANTECIPFERI"], 1000.0)
        self.assertNotIn("ANTECIPFERI", dez)

    def test_sem_data_de_pagamento_nao_ha_adiantamento(self):
        slip = self._recibo("2026-12-01", "2026-12-30", [4000.0])
        self.assertEqual(slip._esocial_competencias_s1200(), ["2026-12"])
        self.assertEqual(
            set(self._por_rubrica(self._s1200(slip, "2026-12"))), {"SAL_BASE"}
        )

    def test_adiantamento_nao_muda_o_fgts_das_competencias_do_gozo(self):
        """1015/9221 têm FGTS 00 e a base de FGTS por parte segue o rateio (11)."""
        regra = self.env.ref("l10n_br_esocial.hr_rule_adiantamento_ferias_esocial")
        desconto = self.env.ref("l10n_br_esocial.hr_rule_desconto_adiantamento_ferias")
        for r in (regra, desconto):
            self.assertEqual(r.l10n_br_esocial_cod_inc_fgts, "00")
            self.assertEqual(r.l10n_br_esocial_cod_inc_cp, "00")
            self.assertEqual(r.l10n_br_esocial_cod_inc_irrf, "13")
        self.assertEqual(regra.l10n_br_esocial_nat_rubr_id.codigo, "1015")
        self.assertEqual(desconto.l10n_br_esocial_nat_rubr_id.codigo, "9221")
        slip = self._recibo("2026-11-10", "2026-12-10", [3100.0])
        antes = [slip._l10n_br_ratear_valor(3100.0, c) for c in ("2026-11", "2026-12")]
        self._pago(slip, "2026-11-07")
        depois = [slip._l10n_br_ratear_valor(3100.0, c) for c in ("2026-11", "2026-12")]
        self.assertEqual(antes, depois)

    def test_gerar_s1200_cria_um_evento_por_competencia(self):
        slip = self._recibo("2026-11-10", "2026-12-10", [3100.0])
        slip.state = "done"
        slip.l10n_br_esocial_data_pagamento = "2026-11-05"
        self.env["hr.payslip"].browse(slip.id).action_esocial_gerar_s1200()
        eventos = self.env["l10n_br.esocial.s1200"].search(
            [("payslip_ids", "in", slip.id)]
        )
        self.assertEqual(sorted(eventos.mapped("per_apur")), ["2026-11", "2026-12"])
        self.assertEqual(slip.l10n_br_esocial_s1200_id.per_apur, "2026-11")
        self.assertEqual(slip.l10n_br_esocial_s1200_ids, eventos)

    # ── IRRF e INSS (MOS S-1210, item 4.1, pp. 186-188) ─────────────────────

    def _recibo_ir(self, de, ate, pago=None, bruto=20000.0, inss=988.09, irrf=4319.55):
        """Recibo de férias com a retenção do IR e o INSS, como o E91 do POC."""
        slip = self._recibo(
            de,
            ate,
            [bruto, inss, irrf],
            {0: "FERIAS", 1: "INSS", 2: "IRRF"},
            {0: self.rule_ferias, 1: self.rule_inss, 2: self.rule_irrf},
        )
        if pago:
            slip.l10n_br_esocial_data_pagamento = pago
        return slip

    def _liquido(self, s1200):
        """Proventos menos descontos do demonstrativo do S-1200 (tpRubr)."""
        regras = self.env["hr.salary.rule"].search([])
        tipo = {}
        for r in regras.filtered("l10n_br_esocial_cod_rubr"):
            tipo[r.l10n_br_esocial_cod_rubr] = r.l10n_br_esocial_tp_rubr
        total = 0.0
        for item in s1200._build_itens_remun():
            sinal = -1 if tipo[item["cod_rubr"]] == "2" else 1
            total += sinal * float(item["vr_rubr"])
        return round(total, 2)

    def test_irrf_retido_inteiro_na_competencia_do_pagamento(self):
        """E91: gozo 20/11 a 19/12 pago em 07/11, IRRF todo no S-1200 de 11."""
        slip = self._recibo_ir("2026-11-20", "2026-12-19", "2026-11-07")
        nov = self._por_rubrica(self._s1200(slip, "2026-11"))
        dez = self._por_rubrica(self._s1200(slip, "2026-12"))
        self.assertEqual(nov["IRRF_F"], 4319.55)
        self.assertNotIn("IRRF_F", dez)

    def test_inss_segue_o_gozo_por_parte_e_soma_o_recibo(self):
        slip = self._recibo_ir("2026-11-20", "2026-12-19", "2026-11-07")
        nov = self._por_rubrica(self._s1200(slip, "2026-11"))
        dez = self._por_rubrica(self._s1200(slip, "2026-12"))
        self.assertEqual(nov["INSS_F"], round(988.09 * 11 / 30, 2))
        self.assertAlmostEqual(nov["INSS_F"] + dez["INSS_F"], 988.09, places=2)

    def test_adiantamento_liquido_do_inss_e_demonstrativos_fecham(self):
        """1015 = 9221 (líquidos do INSS da parte); o líquido de 11 é o do recibo.

        O de 12 fecha em zero: a parte de dezembro já foi paga em 07/11.
        """
        slip = self._recibo_ir("2026-11-20", "2026-12-19", "2026-11-07")
        s_nov, s_dez = self._s1200(slip, "2026-11"), self._s1200(slip, "2026-12")
        nov, dez = self._por_rubrica(s_nov), self._por_rubrica(s_dez)
        parte_dez = round(20000.0 * 19 / 30, 2) - dez["INSS_F"]
        self.assertAlmostEqual(nov["ANTECIPFERI"], parte_dez, places=2)
        self.assertAlmostEqual(dez["DESCANTECIPFERI"], parte_dez, places=2)
        self.assertAlmostEqual(self._liquido(s_nov), 20000.0 - 988.09 - 4319.55, 2)
        self.assertAlmostEqual(self._liquido(s_dez), 0.0, places=2)

    def test_base_do_irrf_do_pagamento_e_a_do_recibo(self):
        """Rendimento 13 menos deduções (41/43) no S-1200 do pagamento = base do recibo.

        A retenção (31 a 34) e a base que ela usa ficam no mesmo demonstrativo.
        """
        slip = self._recibo_ir("2026-11-20", "2026-12-19", "2026-11-07")
        s_nov, s_dez = self._s1200(slip, "2026-11"), self._s1200(slip, "2026-12")

        def base(s1200):
            regras = {
                r.l10n_br_esocial_cod_rubr: r
                for r in self.env["hr.salary.rule"].search(
                    [("l10n_br_esocial_cod_rubr", "!=", False)]
                )
            }
            total = 0.0
            for item in s1200._build_itens_remun():
                regra = regras[item["cod_rubr"]]
                incidencia = regra.l10n_br_esocial_cod_inc_irrf
                valor = float(item["vr_rubr"])
                if incidencia == "13":
                    total += valor if regra.l10n_br_esocial_tp_rubr == "1" else -valor
                elif incidencia in ("41", "43", "53"):
                    total -= valor
            return round(total, 2)

        self.assertAlmostEqual(base(s_nov), 20000.0 - 988.09, places=2)
        self.assertAlmostEqual(base(s_dez), 0.0, places=2)

    def test_deducao_do_ir_que_nao_e_inss_tambem_vai_inteira(self):
        """Pensão alimentícia (IRRF 53) como a retenção: inteira no pagamento."""
        slip = self._recibo(
            "2026-11-20",
            "2026-12-19",
            [20000.0, 500.0],
            {0: "FERIAS", 1: "PENSAO"},
            {1: self.rule_pensao},
        )
        slip.l10n_br_esocial_data_pagamento = "2026-11-07"
        self.assertEqual(
            self._por_rubrica(self._s1200(slip, "2026-11"))["PENSAO_F"], 500.0
        )
        self.assertNotIn("PENSAO_F", self._por_rubrica(self._s1200(slip, "2026-12")))

    def test_sem_data_de_pagamento_a_retencao_fica_na_primeira_competencia(self):
        slip = self._recibo_ir("2026-11-20", "2026-12-19")
        self.assertEqual(slip._esocial_competencia_ir(), "2026-11")
        nov = self._por_rubrica(self._s1200(slip, "2026-11"))
        dez = self._por_rubrica(self._s1200(slip, "2026-12"))
        self.assertEqual(nov["IRRF_F"], 4319.55)
        self.assertNotIn("IRRF_F", dez)

    def test_competencia_do_ir_e_a_do_pagamento_dentro_do_gozo(self):
        """Pago em dezembro, gozo de 11 a 12: a retenção vai ao S-1200 de 12."""
        slip = self._recibo_ir("2026-11-20", "2026-12-19", "2026-12-05")
        self.assertEqual(slip._esocial_competencia_ir(), "2026-12")
        nov = self._por_rubrica(self._s1200(slip, "2026-11"))
        dez = self._por_rubrica(self._s1200(slip, "2026-12"))
        self.assertNotIn("IRRF_F", nov)
        self.assertEqual(dez["IRRF_F"], 4319.55)

    def test_recibo_de_uma_competencia_nao_muda(self):
        slip = self._recibo_ir("2026-11-02", "2026-11-21", "2026-11-01")
        nov = self._por_rubrica(self._s1200(slip, "2026-11"))
        self.assertEqual(nov["IRRF_F"], 4319.55)
        self.assertEqual(nov["INSS_F"], 988.09)
        self.assertNotIn("ANTECIPFERI", nov)

    def test_s1210_aponta_para_o_s1200_da_competencia_do_pagamento(self):
        slip = self._recibo_ir("2026-11-20", "2026-12-19", "2026-11-07")
        slip.state = "done"
        slip.action_esocial_gerar_s1200()
        self.assertEqual(slip.l10n_br_esocial_s1200_id.per_apur, "2026-11")
        # Pago em dezembro (dentro do gozo): o S-1210 vai ao S-1200 de 12.
        outro = self._recibo_ir("2026-11-20", "2026-12-19", "2026-12-05")
        outro.state = "done"
        outro.action_esocial_gerar_s1200()
        self.assertEqual(outro.l10n_br_esocial_s1200_id.per_apur, "2026-12")

    # ── Rubricas 1015/9221: tabela de rubricas da empresa ───────────────────

    def test_tabela_das_rubricas_de_adiantamento_vem_da_empresa(self):
        regras = self.env["hr.salary.rule"]._esocial_regras_adiantamento_ferias()
        self.assertEqual(len(regras), 4)
        for regra in regras:
            self.assertFalse(regra.l10n_br_esocial_ide_tab_rubr)
        self.rule.l10n_br_esocial_ide_tab_rubr = "BASIS"
        self.rule_inss.l10n_br_esocial_ide_tab_rubr = "BASIS"
        for regra in regras:
            self.assertEqual(regra._esocial_ide_tab_rubr_da_regra(), "BASIS")
            self.assertEqual(regra._esocial_chave_rubrica()[1], "BASIS")
        slip = self._recibo("2026-11-10", "2026-12-10", [3100.0])
        self._pago(slip, "2026-11-07")
        itens = self._s1200(slip, "2026-11")._build_itens_remun()
        self.assertEqual({i["ide_tab_rubr"] for i in itens}, {"BASIS"})

    def test_migracao_limpa_a_tabela_1_gravada_nas_rubricas_de_adiantamento(self):
        regras = self.env["hr.salary.rule"]._esocial_regras_adiantamento_ferias()
        regras.write({"l10n_br_esocial_ide_tab_rubr": "1"})
        self.rule.l10n_br_esocial_ide_tab_rubr = "BASIS"
        caminho = Path(__file__).parent.parent / "migrations/18.0.1.8.0"
        spec = importlib.util.spec_from_file_location(
            "migracao_1_8_0", caminho / "post-migration.py"
        )
        migracao = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(migracao)
        migracao.migrate(self.env.cr, "18.0.1.7.0")
        regras.invalidate_recordset()
        for regra in regras:
            self.assertFalse(regra.l10n_br_esocial_ide_tab_rubr)
            self.assertEqual(regra._esocial_ide_tab_rubr_da_regra(), "BASIS")

    # ── TG-152#P3: sem data de pagamento, recusa ─────────────────────────────

    def test_sem_data_de_pagamento_recusa_a_geracao_se_o_gozo_atravessa_o_mes(self):
        slip = self._recibo_ir("2026-11-20", "2026-12-19")
        slip.state = "done"
        with self.assertRaisesRegex(UserError, "Data de Pagamento"):
            slip.action_esocial_gerar_s1200()
        self.assertFalse(slip.l10n_br_esocial_s1200_ids)

    def test_sem_data_de_pagamento_gozo_numa_competencia_segue_como_esta(self):
        slip = self._recibo_ir("2026-11-02", "2026-11-21")
        slip.state = "done"
        slip.action_esocial_gerar_s1200()
        self.assertEqual(slip.l10n_br_esocial_s1200_id.per_apur, "2026-11")

    # ── TG-152#P2: par próprio do abono ──────────────────────────────────────

    def _recibo_abono(self):
        slip = self._recibo(
            "2026-11-20",
            "2026-12-19",
            [15000.0, 5000.0, 4000.0],
            {0: "FERIAS", 1: "ABONO_PECUNIARIO", 2: "INSS"},
            {0: self.rule_ferias, 1: self.rule_abono, 2: self.rule_inss},
        )
        slip.l10n_br_esocial_data_pagamento = "2026-11-07"
        return slip

    def test_parte_futura_do_abono_vai_no_par_proprio(self):
        slip = self._recibo_abono()
        nov = self._por_rubrica(self._s1200(slip, "2026-11"))
        dez = self._por_rubrica(self._s1200(slip, "2026-12"))
        abono_dez = round(5000.0 - round(5000.0 * 11 / 30, 2), 2)
        self.assertEqual(nov["ANTECIPABONO"], abono_dez)
        self.assertEqual(dez["DESCANTECIPABONO"], abono_dez)
        # O 1015 das férias não leva o abono.
        ferias_dez = round(15000.0 - round(15000.0 * 11 / 30, 2), 2)
        inss_dez = round(4000.0 - round(4000.0 * 11 / 30, 2), 2)
        self.assertAlmostEqual(nov["ANTECIPFERI"], ferias_dez - inss_dez, places=2)
        self.assertAlmostEqual(dez["DESCANTECIPFERI"], ferias_dez - inss_dez, places=2)

    def test_par_do_abono_copia_o_irrf_da_rubrica_do_abono_da_empresa(self):
        slip = self._recibo_abono()
        itens = self._s1200(slip, "2026-11")._build_itens_remun()
        self.assertIn("ANTECIPABONO", [i["cod_rubr"] for i in itens])
        for xmlid in (
            "hr_rule_adiantamento_abono_esocial",
            "hr_rule_desconto_adiantamento_abono",
        ):
            regra = self.env.ref("l10n_br_esocial." + xmlid)
            self.assertEqual(regra.l10n_br_esocial_cod_inc_irrf, "75")
            self.assertEqual(regra.l10n_br_esocial_cod_inc_cp, "00")
            self.assertEqual(regra.l10n_br_esocial_cod_inc_fgts, "00")
        self.rule_abono.l10n_br_esocial_cod_inc_irrf = "09"
        self._s1200(slip, "2026-11")._build_itens_remun()
        regra = self.env.ref("l10n_br_esocial.hr_rule_adiantamento_abono_esocial")
        self.assertEqual(regra.l10n_br_esocial_cod_inc_irrf, "09")

    def test_abono_sem_irrf_configurado_recusa_o_par(self):
        slip = self._recibo_abono()
        self.rule_abono.l10n_br_esocial_cod_inc_irrf = False
        self.env["hr.salary.rule"].search(
            [("code", "=", "ABONO_PECUNIARIO"), ("id", "!=", self.rule_abono.id)]
        ).write({"l10n_br_esocial_cod_inc_irrf": False})
        with self.assertRaisesRegex(UserError, "ABONO_PECUNIARIO"):
            self._s1200(slip, "2026-11")._build_itens_remun()

    def test_lote_de_s1010_nao_e_recusado_pelo_par_do_abono_sem_irrf(self):
        """O par do abono sem IRRF fica fora do lote; com IRRF, entra."""
        Regra = self.env["hr.salary.rule"]
        par = Regra._esocial_regras_adiantamento_abono()
        self.env["hr.salary.rule"].search([("code", "=", "ABONO_PECUNIARIO")]).write(
            {"l10n_br_esocial_cod_inc_irrf": False}
        )
        par.write({"l10n_br_esocial_cod_inc_irrf": False})
        S1010 = self.env["l10n_br.esocial.s1010"]
        criados = S1010.criar_para_regras(self.rule | par, "2026-01")
        self.assertEqual(criados.salary_rule_id, self.rule)
        self.rule_abono.l10n_br_esocial_cod_inc_irrf = "75"
        criados = S1010.criar_para_regras(self.rule | par, "2026-01")
        self.assertEqual(criados.salary_rule_id & par, par)
