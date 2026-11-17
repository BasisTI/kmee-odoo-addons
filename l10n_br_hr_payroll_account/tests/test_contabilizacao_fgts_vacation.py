# Copyright 2026 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""
TG-148: contabilização do FGTS sem provisão da rescisão.

As regras de FGTS do saldo de salário e do aviso prévio indenizado do
``l10n_br_hr_vacation`` nasciam sem conta e ficavam fora do lançamento da folha:
o lançamento saía menor que a guia do FGTS Digital. O mapa passa a dar a elas o
débito e o crédito do ``hr_rule_fgts`` (encargos x FGTS a recolher), com a MESMA
conta dele. O FGTS de férias e do 13º fica de fora: as provisões mensais já o
contêm (TG-157 trata da baixa delas).

O ``l10n_br_hr_vacation`` não é dependência do módulo: os testes que precisam
dele são pulados quando ele não está instalado, e um teste próprio prova que o
mapa tolera a regra ausente.
"""
import importlib.util
from datetime import date
from pathlib import Path
from unittest import mock

from odoo.tests import tagged

from odoo.addons.l10n_br_hr_payroll.tests.common import PayrollCommon
from odoo.addons.l10n_br_hr_payroll_account.models import hr_salary_rule

REGRAS_FGTS = (
    "l10n_br_hr_vacation.hr_rule_fgts_aviso",
    "l10n_br_hr_vacation.hr_rule_fgts_rescisao",
)
# FGTS já contido nas provisões PROV_FERIAS_ENC / PROV_13_ENC: fora do mapa.
REGRAS_FORA_DO_MAPA = (
    "l10n_br_hr_vacation.hr_rule_fgts_ferias",
    "l10n_br_hr_vacation.hr_rule_fgts_13_primeira",
    "l10n_br_hr_vacation.hr_rule_fgts_13",
    "l10n_br_hr_vacation.hr_rule_fgts_13_rescisao",
)


@tagged("post_install", "-at_install")
class TestContabilizacaoFgtsVacation(PayrollCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.SalaryRule = cls.env["hr.salary.rule"]
        Account = cls.env["account.account"]
        # Contas mínimas para bases de teste sem plano de contas.
        if not Account.search(
            [("account_type", "=", "expense"), ("company_ids", "in", cls.company.ids)],
            limit=1,
        ):
            Account.create(
                {
                    "name": "Despesas com Pessoal (fixture)",
                    "code": "TST6101",
                    "account_type": "expense",
                    "company_ids": [(6, 0, cls.company.ids)],
                }
            )
        if not Account.search(
            [
                ("account_type", "=", "liability_current"),
                ("company_ids", "in", cls.company.ids),
            ],
            limit=1,
        ):
            Account.create(
                {
                    "name": "Obrigações Trabalhistas (fixture)",
                    "code": "TST2101",
                    "account_type": "liability_current",
                    "company_ids": [(6, 0, cls.company.ids)],
                }
            )
        cls.SalaryRule._l10n_br_setup_payroll_accounts(cls.company)
        cls.journal = cls.env.ref("l10n_br_hr_payroll_account.journal_folha_pagamento")
        cls.fgts_mensal = cls.env.ref("l10n_br_hr_payroll.hr_rule_fgts")
        cls.tem_vacation = bool(
            cls.env["ir.module.module"].search_count(
                [("name", "=", "l10n_br_hr_vacation"), ("state", "=", "installed")]
            )
        )

    def _exige_vacation(self):
        if not self.tem_vacation:
            self.skipTest("l10n_br_hr_vacation não instalado")

    def _slip(self, emp, contract, struct, date_from, date_to, **extra):
        valores = {
            "name": "Holerite FGTS",
            "employee_id": emp.id,
            "contract_id": contract.id,
            "struct_id": struct.id,
            "date_from": date_from,
            "date_to": date_to,
            "company_id": self.company.id,
            "journal_id": self.journal.id,
        }
        valores.update(extra)
        slip = self.env["hr.payslip"].create(valores)
        slip.compute_sheet()
        return slip

    def _soma(self, move, conta, lado):
        return sum(
            move.line_ids.filtered(lambda ln: ln.account_id == conta).mapped(lado)
        )

    def _linhas_de_fgts(self, move, regras):
        nomes = [self.env.ref(xmlid).name for xmlid in regras]
        return move.line_ids.filtered(lambda ln: ln.name in nomes)

    def _confere_lancamento_sem_fgts(self, slip):
        """13º e férias: o FGTS está na provisão, não no lançamento do holerite."""
        self.assertGreater(self._get_line_total(slip, "FGTS"), 0.0)
        slip.action_payslip_done()
        move = slip.move_id
        if move:
            self.assertAlmostEqualMoney(
                sum(move.line_ids.mapped("debit")), sum(move.line_ids.mapped("credit"))
            )
            self.assertFalse(
                self._linhas_de_fgts(move, REGRAS_FORA_DO_MAPA + REGRAS_FGTS),
                "o FGTS do 13º/férias não vai ao lançamento (já está na provisão)",
            )
            self.assertFalse(
                self._soma(move, self.fgts_mensal.account_credit, "credit"),
                "nada a crédito de FGTS a recolher",
            )

    def test_mapa_das_regras_de_fgts_igual_ao_do_mensal(self):
        self._exige_vacation()
        self.assertEqual(self.fgts_mensal.account_debit.account_type, "expense")
        self.assertTrue(
            self.fgts_mensal.account_credit.account_type.startswith("liability")
        )
        for xmlid in REGRAS_FGTS:
            rule = self.env.ref(xmlid)
            self.assertEqual(
                rule.account_debit, self.fgts_mensal.account_debit, xmlid + " débito"
            )
            self.assertEqual(
                rule.account_credit, self.fgts_mensal.account_credit, xmlid + " crédito"
            )

    def test_fgts_de_ferias_e_13_fica_fora_do_mapa(self):
        """O FGTS já está nas provisões: sem conta, não duplica a despesa."""
        self._exige_vacation()
        for xmlid in REGRAS_FORA_DO_MAPA:
            self.assertNotIn(xmlid, hr_salary_rule._RULE_ACCOUNT_MAP)
            rule = self.env.ref(xmlid)
            self.assertFalse(rule.account_debit, xmlid + " débito")
            self.assertFalse(rule.account_credit, xmlid + " crédito")

    def test_decimo_primeira_parcela_nao_lanca_fgts(self):
        self._exige_vacation()
        emp = self._create_employee("FGTS 13º 1ª parcela")
        contract = self._create_contract(emp, wage=5000.0, date_start=date(2020, 1, 1))
        struct = self.env.ref("l10n_br_hr_vacation.structure_13_primeira_parcela")
        slip = self._slip(emp, contract, struct, date(2026, 11, 1), date(2026, 11, 30))
        self._confere_lancamento_sem_fgts(slip)

    def test_decimo_segunda_parcela_nao_lanca_fgts(self):
        self._exige_vacation()
        emp = self._create_employee("FGTS 13º 2ª parcela")
        contract = self._create_contract(emp, wage=5000.0, date_start=date(2020, 1, 1))
        struct = self.env.ref("l10n_br_hr_vacation.structure_13_segunda_parcela")
        slip = self._slip(
            emp,
            contract,
            struct,
            date(2026, 12, 1),
            date(2026, 12, 31),
            l10n_br_primeira_parcela_13_paga=2500.00,
        )
        self._confere_lancamento_sem_fgts(slip)

    def test_rescisao_com_aviso_indenizado_lanca_fgts_do_saldo_e_do_aviso(self):
        self._exige_vacation()
        emp = self._create_employee("FGTS rescisão com aviso")
        contract = self._create_contract(emp, wage=3000.0, date_start=date(2020, 1, 1))
        struct = self.env.ref("l10n_br_hr_vacation.structure_rescisao")
        slip = self._slip(
            emp,
            contract,
            struct,
            date(2026, 6, 1),
            date(2026, 6, 10),
            l10n_br_tipo_rescisao="sem_justa_causa",
            l10n_br_aviso_previo="indenizado",
        )
        aviso = self._get_line_total(slip, "FGTS_AVISO")
        decimo = self._get_line_total(slip, "FGTS_13")
        saldo = self._get_line_total(slip, "FGTS")
        self.assertGreater(aviso, 0.0)
        self.assertGreater(decimo, 0.0, "o holerite calcula o FGTS do 13º")
        self.assertGreater(saldo, 0.0)
        slip.action_payslip_done()
        move = slip.move_id
        self.assertAlmostEqualMoney(
            sum(move.line_ids.mapped("debit")), sum(move.line_ids.mapped("credit"))
        )
        conta_debito = self.fgts_mensal.account_debit
        conta_credito = self.fgts_mensal.account_credit
        for xmlid, valor in (
            ("l10n_br_hr_vacation.hr_rule_fgts_aviso", aviso),
            ("l10n_br_hr_vacation.hr_rule_fgts_rescisao", saldo),
        ):
            linhas = self._linhas_de_fgts(move, [xmlid])
            self.assertTrue(linhas, "linha de %s no lançamento" % xmlid)
            self.assertAlmostEqualMoney(
                sum(
                    linhas.filtered(lambda ln: ln.account_id == conta_debito).mapped(
                        "debit"
                    )
                ),
                valor,
            )
            self.assertAlmostEqualMoney(
                sum(
                    linhas.filtered(lambda ln: ln.account_id == conta_credito).mapped(
                        "credit"
                    )
                ),
                valor,
            )
        # O FGTS do 13º proporcional está na provisão: fora do lançamento.
        self.assertFalse(
            self._linhas_de_fgts(move, ["l10n_br_hr_vacation.hr_rule_fgts_13_rescisao"])
        )
        # Crédito de FGTS a recolher = só o do saldo e o do aviso.
        self.assertAlmostEqualMoney(
            self._soma(move, conta_credito, "credit"), aviso + saldo
        )
        self.assertGreaterEqual(self._soma(move, conta_debito, "debit"), aviso + saldo)

    def _migra(self):
        caminho = (
            Path(hr_salary_rule.__file__).parents[1]
            / "migrations"
            / "18.0.1.1.0"
            / "post-migration.py"
        )
        spec = importlib.util.spec_from_file_location("post_migration_148", caminho)
        modulo = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(modulo)
        modulo.migrate(self.env.cr, "18.0.1.0.0")

    def _regras(self):
        regras = self.env["hr.salary.rule"].browse()
        for xmlid in REGRAS_FGTS:
            regras |= self.env.ref(xmlid)
        return regras

    def _contas_manuais(self):
        Account = self.env["account.account"]
        debito = Account.create(
            {
                "name": "Despesa FGTS do contador",
                "code": "TST6999",
                "account_type": "expense",
                "company_ids": [(6, 0, self.company.ids)],
            }
        )
        credito = Account.create(
            {
                "name": "Passivo do contador",
                "code": "TST2999",
                "account_type": "liability_current",
                "company_ids": [(6, 0, self.company.ids)],
            }
        )
        return debito, credito

    def test_banco_existente_recebe_as_contas_na_migracao(self):
        """Banco que já tinha o módulo: a migração preenche o que faltava."""
        self._exige_vacation()
        regras = self._regras()
        regras.write({"account_debit": False, "account_credit": False})
        self._migra()
        regras.invalidate_recordset()
        for rule in regras:
            self.assertEqual(rule.account_debit, self.fgts_mensal.account_debit)
            self.assertEqual(rule.account_credit, self.fgts_mensal.account_credit)

    def test_migracao_copia_a_conta_manual_do_fgts_mensal(self):
        """Conta configurada à mão no FGTS mensal: as regras novas usam a mesma."""
        self._exige_vacation()
        debito, credito = self._contas_manuais()
        self.fgts_mensal.write({"account_debit": debito, "account_credit": credito})
        regras = self._regras()
        regras.write({"account_debit": False, "account_credit": False})
        self._migra()
        regras.invalidate_recordset()
        for rule in regras:
            self.assertEqual(rule.account_debit, debito, rule.name)
            self.assertEqual(rule.account_credit, credito, rule.name)

    def test_conta_manual_do_mensal_vale_na_instalacao_tardia_do_vacation(self):
        """Caminho do ``_load_records``: regra nova também herda o FGTS mensal."""
        self._exige_vacation()
        debito, credito = self._contas_manuais()
        self.fgts_mensal.write({"account_debit": debito, "account_credit": credito})
        regras = self._regras()
        regras.write({"account_debit": False, "account_credit": False})
        self.SalaryRule._l10n_br_setup_payroll_accounts(self.company)
        for rule in regras:
            self.assertEqual(rule.account_debit, debito, rule.name)
            self.assertEqual(rule.account_credit, credito, rule.name)

    def test_mensal_vazio_cai_no_slot(self):
        self._exige_vacation()
        self.fgts_mensal.write({"account_debit": False, "account_credit": False})
        regras = self._regras()
        regras.write({"account_debit": False, "account_credit": False})
        self.SalaryRule._l10n_br_setup_payroll_accounts(self.company)
        debito = self.SalaryRule._l10n_br_find_account(self.company, "expense_encargos")
        credito = self.SalaryRule._l10n_br_find_account(self.company, "liability_fgts")
        for rule in regras:
            self.assertEqual(rule.account_debit, debito, rule.name)
            self.assertEqual(rule.account_credit, credito, rule.name)

    def test_configuracao_manual_nao_e_sobrescrita(self):
        self._exige_vacation()
        rule = self.env.ref("l10n_br_hr_vacation.hr_rule_fgts_aviso")
        propria = self.env["account.account"].search(
            [
                ("account_type", "=", "expense"),
                ("company_ids", "in", self.company.ids),
            ],
            limit=1,
        )
        rule.account_debit = propria
        self.SalaryRule._l10n_br_setup_payroll_accounts(self.company)
        self.assertEqual(rule.account_debit, propria)

    def test_regra_do_mapa_ausente_e_ignorada(self):
        """Sem o l10n_br_hr_vacation o xmlid não existe e o mapa segue."""
        mapa = dict(hr_salary_rule._RULE_ACCOUNT_MAP)
        mapa["l10n_br_hr_vacation.hr_rule_que_nao_existe"] = {
            "debit": "expense_encargos",
            "credit": "liability_fgts",
        }
        with mock.patch.object(hr_salary_rule, "_RULE_ACCOUNT_MAP", mapa):
            self.assertTrue(
                self.SalaryRule._l10n_br_setup_payroll_accounts(self.company)
            )
        self.assertTrue(self.fgts_mensal.account_debit)
