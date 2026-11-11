# Copyright 2026 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import logging

from odoo.exceptions import ValidationError
from odoo.tests.common import TransactionCase
from odoo.tools import mute_logger


class TestRubricasUnicas(TransactionCase):
    """TG-105: código único por rubrica, natureza correta e aviso no S-1200."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        partner = cls.company.partner_id
        if not partner.vat:
            partner.write({"vat": "02.546.716/0001-46"})
        Rule = cls.env["hr.salary.rule"]
        cls.nat_1000 = cls.env.ref("l10n_br_esocial.nat_rubr_1000")
        cls.nat_4050 = cls.env.ref("l10n_br_esocial.nat_rubr_4050")
        cls.nat_1002 = cls.env.ref("l10n_br_esocial.nat_rubr_1002")
        cls.categoria = cls.env.ref("l10n_br_hr_payroll.hr_salary_rule_category_alw")
        base = {
            "category_id": cls.categoria.id,
            "condition_select": "none",
            "amount_select": "fix",
            "amount_fix": 10.0,
        }
        cls.regra_mensal = Rule.create(
            dict(base, name="Provento mensal", code="T105_MENSAL")
        )
        cls.regra_ferias = Rule.create(
            dict(base, name="Provento férias", code="T105_FERIAS")
        )

    def _config(self, **extra):
        valores = {
            "l10n_br_esocial_cod_rubr": "T105",
            "l10n_br_esocial_ide_tab_rubr": "1",
            "l10n_br_esocial_nat_rubr_id": self.nat_1000.id,
            "l10n_br_esocial_tp_rubr": "1",
            "l10n_br_esocial_cod_inc_cp": "11",
            "l10n_br_esocial_cod_inc_irrf": "11",
            "l10n_br_esocial_cod_inc_fgts": "11",
        }
        valores.update(extra)
        return valores

    # --- código único por rubrica ---------------------------------------

    def test_mesmo_codigo_com_a_mesma_definicao_e_a_mesma_rubrica(self):
        self.regra_mensal.write(self._config())
        self.regra_ferias.write(self._config())
        self.assertEqual(
            self.regra_mensal.l10n_br_esocial_cod_rubr,
            self.regra_ferias.l10n_br_esocial_cod_rubr,
        )

    def test_mesmo_codigo_com_natureza_diferente_e_recusado(self):
        self.regra_mensal.write(self._config())
        with self.assertRaisesRegex(ValidationError, "T105"):
            self.regra_ferias.write(
                self._config(l10n_br_esocial_nat_rubr_id=self.nat_1002.id)
            )

    def test_mesmo_codigo_com_incidencia_diferente_e_recusado(self):
        self.regra_mensal.write(self._config())
        with self.assertRaises(ValidationError):
            self.regra_ferias.write(self._config(l10n_br_esocial_cod_inc_fgts="00"))

    def test_mesmo_codigo_em_tabela_de_rubricas_diferente_e_permitido(self):
        self.regra_mensal.write(self._config())
        self.regra_ferias.write(
            self._config(
                l10n_br_esocial_ide_tab_rubr="2",
                l10n_br_esocial_nat_rubr_id=self.nat_1002.id,
            )
        )

    def test_alterar_uma_regra_do_grupo_e_recusado(self):
        self.regra_mensal.write(self._config())
        self.regra_ferias.write(self._config())
        with self.assertRaises(ValidationError):
            self.regra_mensal.write({"l10n_br_esocial_cod_inc_cp": "00"})

    # --- S-1010 uma vez por rubrica -------------------------------------

    def _s1010(self, regra, **extra):
        valores = {
            "salary_rule_id": regra.id,
            "operacao": "inclusao",
            "ini_valid": "2026-01",
            "company_id": self.company.id,
        }
        valores.update(extra)
        return self.env["l10n_br.esocial.s1010"].create(valores)

    def test_s1010_repetido_para_o_mesmo_codigo_e_recusado(self):
        self.regra_mensal.write(self._config())
        self.regra_ferias.write(self._config())
        self._s1010(self.regra_mensal)
        with self.assertRaisesRegex(ValidationError, "T105"):
            self._s1010(self.regra_ferias)

    def test_s1010_mesmo_codigo_em_outra_validade_e_permitido(self):
        self.regra_mensal.write(self._config())
        self.regra_ferias.write(self._config())
        self._s1010(self.regra_mensal)
        self._s1010(self.regra_ferias, ini_valid="2026-06", operacao="alteracao")

    def test_criar_para_regras_gera_um_s1010_por_rubrica(self):
        self.regra_mensal.write(self._config())
        self.regra_ferias.write(self._config())
        outra = self.env["hr.salary.rule"].create(
            {
                "name": "Outro",
                "code": "T105_OUTRO",
                "category_id": self.categoria.id,
                "condition_select": "none",
                "amount_select": "fix",
                "amount_fix": 1.0,
                **self._config(
                    l10n_br_esocial_cod_rubr="T105B",
                    l10n_br_esocial_nat_rubr_id=self.nat_1002.id,
                ),
            }
        )
        criados = self.env["l10n_br.esocial.s1010"].criar_para_regras(
            self.regra_mensal | self.regra_ferias | outra, "2026-01"
        )
        self.assertEqual(
            sorted(criados.mapped("salary_rule_id.l10n_br_esocial_cod_rubr")),
            ["T105", "T105B"],
        )

    # --- natureza do salário-maternidade --------------------------------

    def test_maternidade_com_natureza_de_salario_comum_e_recusada(self):
        with self.assertRaisesRegex(ValidationError, "4050"):
            self.regra_mensal.write(self._config(l10n_br_esocial_cod_inc_cp="21"))

    def test_maternidade_com_natureza_4050_e_aceita(self):
        self.regra_mensal.write(
            self._config(
                l10n_br_esocial_nat_rubr_id=self.nat_4050.id,
                l10n_br_esocial_cod_inc_cp="21",
            )
        )
        self.assertEqual(self.regra_mensal.l10n_br_esocial_nat_rubr_id.codigo, "4050")

    # --- aviso no S-1200 -------------------------------------------------

    def _s1200_com_linhas(self, regras_valores):
        employee = self.env["hr.employee"].create(
            {
                "name": "Trabalhador T105",
                "cnpj_cpf": "076.166.929-41",
                "l10n_br_esocial_matricula": "MAT105",
                "l10n_br_esocial_categoria_id": self.env.ref(
                    "l10n_br_esocial.cat_trab_101"
                ).id,
            }
        )
        contract = self.env["hr.contract"].create(
            {
                "name": "Contrato T105",
                "employee_id": employee.id,
                "wage": 3000.0,
                "date_start": "2024-01-02",
                "state": "open",
            }
        )
        payslip = self.env["hr.payslip"].create(
            {
                "name": "Holerite T105",
                "employee_id": employee.id,
                "contract_id": contract.id,
                "date_from": "2024-03-01",
                "date_to": "2024-03-31",
            }
        )
        for regra, valor in regras_valores:
            self.env["hr.payslip.line"].create(
                {
                    "slip_id": payslip.id,
                    "salary_rule_id": regra.id,
                    "name": regra.name,
                    "code": regra.code,
                    "employee_id": employee.id,
                    "contract_id": contract.id,
                    "quantity": 1,
                    "amount": valor,
                    "rate": 100,
                }
            )
        return self.env["l10n_br.esocial.s1200"].create(
            {
                "employee_id": employee.id,
                "payslip_ids": [(6, 0, payslip.ids)],
                "per_apur": "2024-03",
                "ind_apuracao": "1",
                "company_id": self.company.id,
            }
        )

    def test_regra_sem_natureza_com_valor_gera_aviso(self):
        self.regra_mensal.write(self._config())
        # regra_ferias fica sem configuração eSocial
        s1200 = self._s1200_com_linhas(
            [(self.regra_mensal, 100.0), (self.regra_ferias, 50.0)]
        )
        with self.assertLogs(
            "odoo.addons.l10n_br_esocial.models.intermediarios.s1200_remuneracao",
            level=logging.WARNING,
        ) as logs:
            itens = s1200._build_itens_remun()
        self.assertEqual([i["cod_rubr"] for i in itens], ["T105"])
        self.assertIn("T105_FERIAS", s1200.avisos)
        self.assertIn("natureza da rubrica", s1200.avisos)
        self.assertIn("T105_FERIAS", logs.output[0])

    def test_regra_sem_valor_ou_configurada_nao_gera_aviso(self):
        self.regra_mensal.write(self._config())
        s1200 = self._s1200_com_linhas(
            [(self.regra_mensal, 100.0), (self.regra_ferias, 0.0)]
        )
        with mute_logger(
            "odoo.addons.l10n_br_esocial.models.intermediarios.s1200_remuneracao"
        ):
            s1200._build_itens_remun()
        self.assertFalse(s1200.avisos)
