# Copyright 2026 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""TG-149: o aprendiz recolhe FGTS de 2% e INSS pela tabela nas férias e na rescisão.

Lei 8.036/90, art. 15, § 7º (FGTS de 2% no contrato de aprendizagem); o INSS do
aprendiz segue a tabela comum, como no empregado comum.
"""
from datetime import date

from odoo.tests import tagged

from odoo.addons.l10n_br_hr_payroll.models.salary_rules_br import round_money

from .common import VacationCommon


@tagged("post_install", "-at_install")
class TestAprendizFgtsInss(VacationCommon):
    def _contrato(self, nome, aprendiz=True, wage=2500.00):
        emp = self._create_employee(nome)
        if aprendiz:
            emp.l10n_br_tipo_contrato = "aprendiz"
        contract = self._create_contract(emp, wage=wage, date_start=date(2020, 1, 1))
        return emp, contract

    def _holerite(self, emp, contract, struct, de, ate, **extra):
        valores = {
            "name": "Holerite %s" % de,
            "employee_id": emp.id,
            "contract_id": contract.id,
            "struct_id": struct.id,
            "date_from": de,
            "date_to": ate,
            "company_id": self.env.company.id,
        }
        valores.update(extra)
        slip = self.env["hr.payslip"].create(valores)
        slip.compute_sheet()
        return slip

    def _ferias(self, emp, contract):
        return self._holerite(
            emp, contract, self.structure_ferias, date(2024, 5, 1), date(2024, 5, 30)
        )

    def _rescisao(self, emp, contract, ate=None, **extra):
        ate = ate or date(2026, 12, 10)
        valores = {
            "l10n_br_tipo_rescisao": "sem_justa_causa",
            "l10n_br_aviso_previo": "trabalhado",
            "l10n_br_fgts_saldo_conta": 10000.00,
        }
        valores.update(extra)
        return self._holerite(
            emp, contract, self.structure_rescisao, ate.replace(day=1), ate, **valores
        )

    # --- férias --------------------------------------------------------------

    def test_ferias_fgts_2_por_cento_e_inss_pela_tabela(self):
        emp, contract = self._contrato("Aprendiz férias")
        slip = self._ferias(emp, contract)
        gross = self._get_line_total(slip, "GROSS")
        self.assertGreater(gross, 0)
        self.assertAlmostEqualMoney(
            self._get_line_total(slip, "FGTS"), round_money(gross * 0.02)
        )
        comum, contrato_comum = self._contrato("Comum férias", aprendiz=False)
        slip_comum = self._ferias(comum, contrato_comum)
        self.assertAlmostEqualMoney(
            self._get_line_total(slip_comum, "FGTS"),
            round_money(self._get_line_total(slip_comum, "GROSS") * 0.08),
        )
        self.assertAlmostEqualMoney(
            self._get_line_total(slip, "INSS"),
            self._get_line_total(slip_comum, "INSS"),
        )
        self.assertGreater(self._get_line_total(slip, "INSS"), 0)

    # --- rescisão ------------------------------------------------------------

    def test_rescisao_saldo_fgts_2_por_cento_e_inss_pela_tabela(self):
        emp, contract = self._contrato("Aprendiz saldo")
        resc = self._rescisao(emp, contract)
        saldo = self._get_line_total(resc, "SALDO_SALARIO")
        self.assertGreater(saldo, 0)
        self.assertAlmostEqualMoney(
            self._get_line_total(resc, "FGTS"), round_money(saldo * 0.02)
        )
        comum, contrato_comum = self._contrato("Comum saldo", aprendiz=False)
        resc_comum = self._rescisao(comum, contrato_comum)
        self.assertAlmostEqualMoney(
            self._get_line_total(resc, "INSS"),
            self._get_line_total(resc_comum, "INSS"),
        )
        self.assertGreater(self._get_line_total(resc, "INSS"), 0)

    def test_rescisao_inss_do_13o_pela_tabela(self):
        emp, contract = self._contrato("Aprendiz 13º")
        resc = self._rescisao(emp, contract)
        devido = self._get_line_total(resc, "DECIMO_DEVIDO")
        self.assertGreater(devido, 0)
        comum, contrato_comum = self._contrato("Comum 13º", aprendiz=False)
        resc_comum = self._rescisao(comum, contrato_comum)
        self.assertGreater(self._get_line_total(resc, "INSS_13"), 0)
        self.assertAlmostEqualMoney(
            self._get_line_total(resc, "INSS_13"),
            self._get_line_total(resc_comum, "INSS_13"),
        )

    def test_rescisao_aviso_indenizado_fgts_2_por_cento(self):
        emp, contract = self._contrato("Aprendiz aviso")
        resc = self._rescisao(emp, contract, l10n_br_aviso_previo="indenizado")
        aviso = self._get_line_total(resc, "AVISO_PREVIO_INDENIZADO")
        self.assertGreater(aviso, 0)
        self.assertAlmostEqualMoney(
            self._get_line_total(resc, "FGTS_AVISO"), round_money(aviso * 0.02)
        )

    def test_comum_continua_com_8_por_cento(self):
        emp, contract = self._contrato("Comum 8%", aprendiz=False)
        resc = self._rescisao(emp, contract)
        saldo = self._get_line_total(resc, "SALDO_SALARIO")
        self.assertAlmostEqualMoney(
            self._get_line_total(resc, "FGTS"), round_money(saldo * 0.08)
        )
