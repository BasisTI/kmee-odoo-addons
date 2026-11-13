# Copyright 2026 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""TG-93 r2: FGTS do 13º com 1ª parcela e rescisão no mesmo ano.

A 1ª parcela recolhe o FGTS dela na competência do pagamento; a rescisão do
mesmo ano recolhe só o que falta do 13º proporcional (sem valor negativo), e a
base da multa soma TODO o FGTS depositado do 13º (1ª parcela mais rescisão).
"""
from datetime import date

from odoo.exceptions import ValidationError
from odoo.tests import tagged

from odoo.addons.l10n_br_hr_payroll.models.salary_rules_br import round_money

from .common import VacationCommon


@tagged("post_install", "-at_install")
class TestFgts13PrimeiraParcelaRescisao(VacationCommon):
    def _primeira_parcela(self, emp, contract, confirmar=True, mes=11):
        slip = self.env["hr.payslip"].create(
            {
                "name": "13º 1ª parcela",
                "employee_id": emp.id,
                "contract_id": contract.id,
                "struct_id": self.structure_13_primeira.id,
                "date_from": date(2026, mes, 1),
                "date_to": date(2026, mes, 28),
                "company_id": self.env.company.id,
            }
        )
        slip.compute_sheet()
        if confirmar:
            slip.action_payslip_done()
        return slip

    def _rescisao(self, emp, contract, ate, **extra):
        valores = {
            "name": "Rescisão",
            "employee_id": emp.id,
            "contract_id": contract.id,
            "struct_id": self.structure_rescisao.id,
            "date_from": ate.replace(day=1),
            "date_to": ate,
            "l10n_br_tipo_rescisao": "pedido_demissao",
            "l10n_br_aviso_previo": "nao_aplicavel",
            "company_id": self.env.company.id,
        }
        valores.update(extra)
        resc = self.env["hr.payslip"].create(valores)
        resc.compute_sheet()
        return resc

    def _contrato(self, nome="FGTS 13º 1ª parcela + rescisão"):
        emp = self._create_employee(nome)
        contract = self._create_contract(emp, wage=2500.00, date_start=date(2020, 1, 1))
        return emp, contract

    def test_rescisao_abate_o_fgts_ja_recolhido_na_primeira_parcela(self):
        """Caso P002 (D01 + R02): 100,00 na 1ª parcela + 83,33 na rescisão."""
        emp, contract = self._contrato()
        primeira = self._primeira_parcela(emp, contract)
        self.assertAlmostEqualMoney(self._get_line_total(primeira, "FGTS"), 100.00)
        resc = self._rescisao(emp, contract, date(2026, 12, 10))
        decimo = self._get_line_total(resc, "DECIMO_RESCISAO")
        total_devido = round_money(decimo * 0.08)
        self.assertAlmostEqualMoney(total_devido, 183.33)
        self.assertAlmostEqualMoney(self._get_line_total(resc, "FGTS_13"), 83.33)
        self.assertAlmostEqualMoney(
            100.00 + self._get_line_total(resc, "FGTS_13"), total_devido
        )

    def test_sem_primeira_parcela_confirmada_a_rescisao_recolhe_tudo(self):
        """1ª parcela em rascunho não conta como recolhida."""
        emp, contract = self._contrato("FGTS 13º 1ª parcela em rascunho")
        self._primeira_parcela(emp, contract, confirmar=False)
        resc = self._rescisao(emp, contract, date(2026, 12, 10))
        self.assertAlmostEqualMoney(self._get_line_total(resc, "FGTS_13"), 183.33)

    def test_primeira_parcela_maior_que_o_proporcional_zera_o_fgts_da_rescisao(self):
        """FGTS da rescisão nunca é negativo: 1ª parcela de 100,00 contra um
        13º proporcional de fevereiro (poucos avos)."""
        emp, contract = self._contrato("FGTS 13º 1ª parcela maior")
        # 1ª parcela adiantada em janeiro; rescisão em fevereiro.
        self._primeira_parcela(emp, contract, mes=1)
        resc = self._rescisao(emp, contract, date(2026, 2, 10))
        decimo = self._get_line_total(resc, "DECIMO_RESCISAO")
        self.assertLess(round_money(decimo * 0.08), 100.00)
        self.assertEqual(self._get_line_total(resc, "FGTS_13"), 0.0)

    def test_base_da_multa_soma_o_fgts_da_primeira_parcela_e_da_rescisao(self):
        emp, contract = self._contrato("FGTS 13º base da multa")
        self._primeira_parcela(emp, contract)
        resc = self._rescisao(
            emp,
            contract,
            date(2026, 12, 10),
            l10n_br_tipo_rescisao="sem_justa_causa",
            l10n_br_aviso_previo="indenizado",
            l10n_br_fgts_saldo_conta=10000.00,
        )
        depositos = (
            self._get_line_total(resc, "FGTS")
            + self._get_line_total(resc, "FGTS_13")
            + 100.00
            + self._get_line_total(resc, "FGTS_AVISO")
        )
        self.assertAlmostEqualMoney(
            self._get_line_total(resc, "MULTA_FGTS"),
            round_money((10000.00 + depositos) * 0.40),
        )

    def test_confirmar_a_primeira_parcela_recalcula_a_rescisao_aberta(self):
        emp, contract = self._contrato("FGTS 13º recalcula")
        primeira = self._primeira_parcela(emp, contract, confirmar=False)
        resc = self._rescisao(emp, contract, date(2026, 12, 10))
        self.assertAlmostEqualMoney(self._get_line_total(resc, "FGTS_13"), 183.33)
        primeira.action_payslip_done()
        self.assertAlmostEqualMoney(self._get_line_total(resc, "FGTS_13"), 83.33)

    def test_primeira_parcela_negativa_e_recusada(self):
        emp, contract = self._contrato("FGTS 13º negativa")
        with self.assertRaises(ValidationError):
            self.env["hr.payslip"].create(
                {
                    "name": "13º 2ª negativa",
                    "employee_id": emp.id,
                    "contract_id": contract.id,
                    "struct_id": self.structure_13_segunda.id,
                    "date_from": date(2026, 12, 1),
                    "date_to": date(2026, 12, 31),
                    "l10n_br_primeira_parcela_13_paga": -100.00,
                    "company_id": self.env.company.id,
                }
            )
