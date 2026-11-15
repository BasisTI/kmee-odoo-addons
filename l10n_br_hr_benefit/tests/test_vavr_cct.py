# Copyright 2026 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""TG-111: desconto de VA/VR (071) por faixa da CCT e VT com o percentual da CCT."""
from datetime import date

from odoo.exceptions import UserError

from odoo.addons.l10n_br_hr_benefit.models.vale_transporte import desconto_vt
from odoo.addons.l10n_br_hr_payroll.tests.common import PayrollCommon


class TestDescontoVaVrCct(PayrollCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.template_vr = cls.env.ref("l10n_br_hr_benefit.advantage_template_vr")
        cls.template_va = cls.env.ref("l10n_br_hr_benefit.advantage_template_va")
        cls.template_vt = cls.env.ref("l10n_br_hr_benefit.advantage_template_vt")
        cls.sindicato = cls.env["res.partner"].create(
            {"name": "Sindicato VA/VR", "union_entity_code": "SVV", "is_company": True}
        )
        Cct = cls.env["l10n.br.hr.collective.convention"]
        cls.cct1 = Cct.create(
            {
                "name": "CCT VA/VR 1",
                "partner_union_id": cls.sindicato.id,
                "date_start": date(2024, 1, 1),
                "date_end": date(2024, 5, 31),
                "vt_employee_pct": 5.0,
            }
        )
        cls.cct2 = Cct.create(
            {
                "name": "CCT VA/VR 2",
                "partner_union_id": cls.sindicato.id,
                "date_start": date(2024, 6, 1),
                "date_end": date(2024, 12, 31),
                "vt_employee_pct": 8.0,
            }
        )
        Faixa = cls.env["l10n.br.hr.convention.vavr.range"]
        Faixa.create(
            [
                {"convention_id": cls.cct1.id, "wage_ceiling": 3000, "rate_pct": 1},
                {"convention_id": cls.cct1.id, "wage_ceiling": 6000, "rate_pct": 10},
                {"convention_id": cls.cct1.id, "wage_ceiling": 0, "rate_pct": 20},
                {"convention_id": cls.cct2.id, "wage_ceiling": 0, "rate_pct": 30},
            ]
        )

    def _contrato(self, wage, vr=800.0, va=400.0, cct=None):
        emp = self._create_employee()
        contract = self._create_contract(emp, wage=wage)
        if cct:
            contract.l10n_br_cct_id = cct
        for template, valor in ((self.template_vr, vr), (self.template_va, va)):
            if valor:
                self.env["hr.contract.advantage"].create(
                    {
                        "contract_id": contract.id,
                        "advantage_template_id": template.id,
                        "amount": valor,
                    }
                )
        return emp, contract

    def _desconto(self, wage, **kw):
        emp, contract = self._contrato(wage, **kw)
        return self._get_line_total(self._create_payslip(emp, contract), "DESC_VAVR")

    def test_taxa_da_faixa_do_salario(self):
        """(VR + VA) x taxa da faixa; o teto da faixa é inclusive."""
        self.assertAlmostEqualMoney(self._desconto(2000, cct=self.cct1), 12.0)
        self.assertAlmostEqualMoney(self._desconto(3000, cct=self.cct1), 12.0)
        self.assertAlmostEqualMoney(self._desconto(3000.01, cct=self.cct1), 120.0)
        self.assertAlmostEqualMoney(self._desconto(6000, cct=self.cct1), 120.0)

    def test_faixa_aberta_acima_de(self):
        self.assertAlmostEqualMoney(self._desconto(20000, cct=self.cct1), 240.0)

    def test_so_va_ou_so_vr(self):
        self.assertAlmostEqualMoney(self._desconto(2000, vr=0, cct=self.cct1), 4.0)
        self.assertAlmostEqualMoney(self._desconto(2000, va=0, cct=self.cct1), 8.0)

    def test_vigencia_pela_competencia(self):
        """A competência escolhe a CCT vigente: em junho vale a sucessora."""
        emp, contract = self._contrato(2000, cct=self.cct1)
        marco = self._create_payslip(emp, contract)
        junho = self._create_payslip(
            emp, contract, date_from=date(2024, 6, 1), date_to=date(2024, 6, 30)
        )
        self.assertAlmostEqualMoney(self._get_line_total(marco, "DESC_VAVR"), 12.0)
        self.assertAlmostEqualMoney(self._get_line_total(junho, "DESC_VAVR"), 360.0)

    def test_sem_cct_ou_sem_faixa_nao_desconta(self):
        self.assertEqual(self._desconto(2000), 0.0)
        sem_faixa = self.env["l10n.br.hr.collective.convention"].create(
            {
                "name": "CCT sem faixa",
                "partner_union_id": self.env["res.partner"]
                .create({"name": "Sind. 2", "union_entity_code": "SV2"})
                .id,
                "date_start": date(2024, 1, 1),
                "date_end": date(2024, 12, 31),
            }
        )
        self.assertEqual(self._desconto(2000, cct=sem_faixa), 0.0)

    def test_sem_vr_nem_va_nao_desconta(self):
        self.assertEqual(self._desconto(2000, vr=0, va=0, cct=self.cct1), 0.0)

    def test_desconto_vt_usa_percentual_da_cct(self):
        """CCT de 5%: o VT desconta 5% (cct1); a de 8% fica limitada a 6%."""
        for cct, esperado in ((self.cct1, 100.0), (self.cct2, 120.0)):
            emp, contract = self._contrato(2000, vr=0, va=0, cct=cct)
            self.env["hr.contract.advantage"].create(
                {
                    "contract_id": contract.id,
                    "advantage_template_id": self.template_vt.id,
                    "amount": 500.0,
                }
            )
            data = (
                {}
                if cct == self.cct1
                else {"date_from": date(2024, 6, 1), "date_to": date(2024, 6, 30)}
            )
            payslip = self._create_payslip(emp, contract, **data)
            self.assertAlmostEqualMoney(
                self._get_line_total(payslip, "DESC_VT"), esperado
            )

    def test_desconto_vt_funcao_pura(self):
        self.assertEqual(desconto_vt(2000, 500), 120.0)
        self.assertEqual(desconto_vt(2000, 500, 0.0), 120.0)
        self.assertEqual(desconto_vt(2000, 500, 5.0), 100.0)
        self.assertEqual(desconto_vt(2000, 500, 8.0), 120.0)
        self.assertEqual(desconto_vt(2000, 50, 5.0), 50.0)

    def test_confirmado_vigente_recusa_mudar_vr(self):
        hoje = date.today()
        cct = self.env["l10n.br.hr.collective.convention"].create(
            {
                "name": "CCT hoje",
                "partner_union_id": self.env["res.partner"]
                .create({"name": "Sind. hoje", "union_entity_code": "SHJ"})
                .id,
                "date_start": date(hoje.year, 1, 1),
                "date_end": date(hoje.year, 12, 31),
            }
        )
        self.env["l10n.br.hr.convention.vavr.range"].create(
            {"convention_id": cct.id, "wage_ceiling": 0, "rate_pct": 10}
        )
        emp, contract = self._contrato(2000, cct=cct)
        contract.date_start = date(hoje.year - 1, 1, 1)
        payslip = self.env["hr.payslip"].create(
            {
                "name": "Holerite vigente",
                "employee_id": emp.id,
                "contract_id": contract.id,
                "struct_id": contract.struct_id.id,
                "date_from": hoje.replace(day=1),
                "date_to": hoje.replace(day=28),
                "company_id": self.env.company.id,
            }
        )
        payslip.compute_sheet()
        self.assertAlmostEqualMoney(self._get_line_total(payslip, "DESC_VAVR"), 120.0)
        # Aberto: o recálculo acompanha o VR.
        vr = contract.advantages_ids.filtered(
            lambda a: a.advantage_template_code == "VR"
        )
        vr.amount = 1800.0
        self.assertAlmostEqualMoney(self._get_line_total(payslip, "DESC_VAVR"), 220.0)
        payslip.action_payslip_done()
        with self.assertRaises(UserError):
            vr.amount = 900.0
