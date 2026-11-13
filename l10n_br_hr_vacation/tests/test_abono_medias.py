# Copyright 2024 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""
Testes: o abono pecuniário e o seu 1/3 levam as médias (TG-94).

CLT art. 143 §1º: o abono é pago pela remuneração que o empregado teria nos
dias vendidos, e a remuneração das férias leva a média das verbas variáveis
habituais (Súmula 45 TST / CLT art. 142). Abono e 1/3 do abono continuam sem
INSS e sem FGTS; o 1/3 segue tributável pelo IRRF (COSIT 209/2021).
"""
from datetime import date

from dateutil.relativedelta import relativedelta

from odoo.tests import tagged

from .common import VacationCommon


@tagged("post_install", "-at_install")
class TestAbonoMedias(VacationCommon):
    def _mensal_done(self, emp, contract, ano, mes, he_50):
        payslip = self.env["hr.payslip"].create(
            {
                "name": f"Mensal {mes}/{ano}",
                "employee_id": emp.id,
                "contract_id": contract.id,
                "struct_id": self.structure_clt.id,
                "date_from": date(ano, mes, 1),
                "date_to": date(ano, mes, 1) + relativedelta(day=31),
                "l10n_br_horas_extras_50": he_50,
                "company_id": self.env.company.id,
            }
        )
        payslip.compute_sheet()
        payslip.action_payslip_done()
        return payslip

    def _ferias_com_abono(self, emp, contract, **extra):
        vals = {
            "name": "Férias com abono",
            "employee_id": emp.id,
            "contract_id": contract.id,
            "struct_id": self.structure_ferias.id,
            "date_from": date(2025, 1, 1),
            "date_to": date(2025, 1, 30),
            "l10n_br_abono_pecuniario": True,
            "company_id": self.env.company.id,
        }
        vals.update(extra)
        payslip = self.env["hr.payslip"].create(vals)
        payslip.compute_sheet()
        return payslip

    def _historico(self, emp, contract):
        """6 meses com 10h e 6 com 20h de HE 50%; devolve a média mensal."""
        valores = []
        for mes in range(1, 13):
            mensal = self._mensal_done(
                emp, contract, 2024, mes, 10.0 if mes <= 6 else 20.0
            )
            valores.append(
                self._get_line_total(mensal, "HE_50")
                + self._get_line_total(mensal, "DSR_HE")
            )
        return round(sum(valores) / len(valores), 2)

    def test_abono_e_terco_com_media(self):
        emp = self._create_employee()
        contract = self._create_contract(emp, wage=3000.00, date_start=date(2023, 1, 1))
        media = self._historico(emp, contract)
        self.assertGreater(media, 0.0)
        payslip = self._ferias_com_abono(emp, contract)

        base = 3000.00 + media
        ferias = self._get_line_total(payslip, "FERIAS")
        abono = self._get_line_total(payslip, "ABONO_PECUNIARIO")
        terco_abono = self._get_line_total(payslip, "ADICIONAL_ABONO")
        self.assertAlmostEqualMoney(ferias, base * 20 / 30)
        self.assertAlmostEqualMoney(abono, base * 10 / 30)
        self.assertAlmostEqualMoney(terco_abono, round(abono / 3, 2))

    def test_abono_sem_inss_e_sem_fgts(self):
        """Abono e terço não entram no GROSS (base de INSS e FGTS)."""
        emp = self._create_employee()
        contract = self._create_contract(emp, wage=3000.00, date_start=date(2023, 1, 1))
        self._historico(emp, contract)
        payslip = self._ferias_com_abono(emp, contract)
        ferias = self._get_line_total(payslip, "FERIAS")
        adicional = self._get_line_total(payslip, "ADICIONAL_FERIAS")
        self.assertAlmostEqualMoney(
            self._get_line_total(payslip, "GROSS"), ferias + adicional
        )

    def test_abono_sem_historico_segue_so_salario(self):
        emp = self._create_employee()
        contract = self._create_contract(emp, wage=3000.00, date_start=date(2024, 1, 1))
        payslip = self._ferias_com_abono(emp, contract)
        self.assertAlmostEqualMoney(
            self._get_line_total(payslip, "ABONO_PECUNIARIO"), 1000.00
        )
