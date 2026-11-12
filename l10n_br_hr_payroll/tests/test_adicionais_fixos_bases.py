# Copyright 2026 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""TG-88: periculosidade e insalubridade compõem as bases do holerite mensal.

As duas rubricas estão na categoria ``ALW`` e, por isso, entram no ``GROSS``,
de onde saem as bases do INSS, do FGTS e do IRRF. Os testes provam isso (e
protegem contra quem tirar a rubrica do ``GROSS``).
"""
from datetime import date

from .common import PayrollCommon

MAR_INI, MAR_FIM = date(2026, 3, 1), date(2026, 3, 31)


class TestAdicionaisFixosBases(PayrollCommon):
    def _mensal(self, **flags):
        emp = self._create_employee()
        contract = self._create_contract(emp, wage=3000.0)
        contract.write(flags)
        return self._create_payslip(emp, contract, MAR_INI, MAR_FIM)

    def _bases(self, slip):
        return {
            codigo: self._get_line_total(slip, codigo)
            for codigo in ("GROSS", "INSS", "BASE_IRRF", "FGTS")
        }

    def test_periculosidade_compoe_inss_fgts_e_irrf(self):
        sem = self._bases(self._mensal())
        com = self._bases(self._mensal(l10n_br_periculosidade=True))
        self.assertAlmostEqualMoney(com["GROSS"] - sem["GROSS"], 900.0)
        # FGTS: 8% sobre os 900 a mais.
        self.assertAlmostEqualMoney(com["FGTS"] - sem["FGTS"], 72.0)
        self.assertGreater(com["INSS"], sem["INSS"])
        self.assertGreater(com["BASE_IRRF"], sem["BASE_IRRF"])

    def test_insalubridade_compoe_inss_fgts_e_irrf(self):
        sem = self._bases(self._mensal())
        slip = self._mensal(
            l10n_br_insalubridade=True, l10n_br_grau_insalubridade="medio"
        )
        com = self._bases(slip)
        adicional = self._get_line_total(slip, "ADICIONAL_INSALUBRIDADE")
        self.assertGreater(adicional, 0)
        self.assertAlmostEqualMoney(com["GROSS"] - sem["GROSS"], adicional)
        self.assertAlmostEqualMoney(com["FGTS"] - sem["FGTS"], adicional * 0.08)
        self.assertGreater(com["INSS"], sem["INSS"])
        self.assertGreater(com["BASE_IRRF"], sem["BASE_IRRF"])

    def test_adicionais_fixos_da_ferramenta(self):
        """``tools.br.adicionais_fixos``: valor cheio, sem proporcionalidade."""
        emp = self._create_employee()
        contract = self._create_contract(emp, wage=3000.0)
        slip = self._create_payslip(emp, contract, MAR_INI, MAR_FIM)
        self.assertEqual(slip._l10n_br_adicionais_fixos(contract), 0.0)
        contract.l10n_br_periculosidade = True
        self.assertAlmostEqualMoney(slip._l10n_br_adicionais_fixos(contract), 900.0)
        contract.write(
            {
                "l10n_br_periculosidade": False,
                "l10n_br_insalubridade": True,
                "l10n_br_grau_insalubridade": "maximo",
            }
        )
        salario_minimo = self.env["l10n_br.hr.payroll.inss.faixa"]._salario_minimo(
            MAR_FIM
        )
        self.assertAlmostEqualMoney(
            slip._l10n_br_adicionais_fixos(contract), round(salario_minimo * 0.4, 2)
        )
