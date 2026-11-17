# Copyright 2026 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""TG-152: férias que atravessam o mês no S-1200, rateadas por dias de gozo.

MOS do eSocial S-1.3, S-1010, item 23 (pp. 112-114), exemplo (c): gozo de
10/11 a 10/12 vai ao S-1200 de cada competência, rateado por dias. O exemplo diz
"20 + 10"; a contagem de dias corridos inclusiva dá 21 + 10 (o MOS é impreciso).
"""

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
        cls.estrutura = cls.env["hr.payroll.structure"].search(
            [("code", "=", "FERIAS")], limit=1
        ) or cls.env["hr.payroll.structure"].create(
            {"name": "Férias (teste)", "code": "FERIAS"}
        )

    def _recibo(self, de, ate, valores, codigos=None):
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
                    "salary_rule_id": self.rule.id,
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
        self.env["hr.payslip"].browse(slip.id).action_esocial_gerar_s1200()
        eventos = self.env["l10n_br.esocial.s1200"].search(
            [("payslip_ids", "in", slip.id)]
        )
        self.assertEqual(sorted(eventos.mapped("per_apur")), ["2026-11", "2026-12"])
        self.assertEqual(slip.l10n_br_esocial_s1200_id.per_apur, "2026-11")
        self.assertEqual(slip.l10n_br_esocial_s1200_ids, eventos)
