# Copyright 2024 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""TG-127: DSR entre holerites com afastamento (hr.leave) e com falta tardia.

Só ações padrão da tela: lançar falta, validar e recusar afastamento. Nenhum
teste chama compute_sheet() no dependente para "consertar" o estado.
"""

from datetime import date

from odoo.exceptions import UserError, ValidationError

from .common import PayrollCommon

FEV = (date(2024, 2, 1), date(2024, 2, 29))
MAR = (date(2024, 3, 1), date(2024, 3, 31))
JAN = (date(2024, 1, 1), date(2024, 1, 31))


class TestDsrAfastamento(PayrollCommon):
    def _tipo(self, validacao="hr"):
        return self.env["hr.leave.type"].create(
            {
                "name": "Afastamento INSS (teste)",
                "requires_allocation": "no",
                "leave_validation_type": validacao,
                "l10n_br_afastamento_inss": True,
            }
        )

    def _contrato(self):
        emp = self._create_employee()
        return emp, self._create_contract(emp, wage=3000.00)

    def _holerite(self, emp, contract, periodo, datas=(), faltas=None, **extra):
        slip = self._create_payslip(emp, contract, *periodo)
        slip.write(
            {
                "l10n_br_faltas_injustificadas": faltas
                if faltas is not None
                else len(datas),
                "l10n_br_falta_ids": [
                    (0, 0, dict({"date": d}, **extra)) for d in datas
                ],
            }
        )
        slip.compute_sheet()
        return slip

    def _afastamento(self, emp, tipo, ini, fim):
        return self.env["hr.leave"].create(
            {
                "employee_id": emp.id,
                "holiday_status_id": tipo.id,
                "request_date_from": ini,
                "request_date_to": fim,
            }
        )

    def _dsr(self, slip):
        return self._get_line_total(slip, "DESC_DSR")

    def test_validar_e_recusar_afastamento_recalcula_o_dsr_aberto(self):
        emp, contract = self._contrato()
        mar = self._holerite(emp, contract, MAR, [date(2024, 3, 6)])
        self.assertAlmostEqualMoney(self._dsr(mar), 100.00)
        leave = self._afastamento(emp, self._tipo(), date(2024, 3, 5), date(2024, 3, 8))
        # Pendente de aprovação: ainda não afasta ninguém.
        self.assertAlmostEqualMoney(self._dsr(mar), 100.00)
        leave.sudo().action_validate()
        self.assertEqual(leave.state, "validate")
        self.assertAlmostEqualMoney(self._dsr(mar), 0.0)
        leave.sudo().action_refuse()
        self.assertAlmostEqualMoney(self._dsr(mar), 100.00)

    def test_afastamento_aprovado_na_criacao_recalcula_o_dsr_aberto(self):
        emp, contract = self._contrato()
        mar = self._holerite(emp, contract, MAR, [date(2024, 3, 6)])
        leave = self._afastamento(
            emp, self._tipo("no_validation"), date(2024, 3, 5), date(2024, 3, 8)
        )
        self.assertEqual(leave.state, "validate")
        self.assertAlmostEqualMoney(self._dsr(mar), 0.0)
        leave.sudo().action_refuse()
        self.assertAlmostEqualMoney(self._dsr(mar), 100.00)

    def test_afastamento_passa_a_semana_para_o_outro_mes(self):
        """A falta de 29/02 sai do afastamento: o repouso passa a ser de março."""
        emp, contract = self._contrato()
        fev = self._holerite(emp, contract, FEV, [date(2024, 2, 29)])
        mar = self._holerite(emp, contract, MAR, [date(2024, 3, 1)])
        self.assertAlmostEqualMoney(self._dsr(fev), 100.00)
        self.assertAlmostEqualMoney(self._dsr(mar), 0.0)
        leave = self._afastamento(
            emp, self._tipo(), date(2024, 2, 28), date(2024, 2, 29)
        )
        leave.sudo().action_validate()
        self.assertAlmostEqualMoney(self._dsr(fev), 0.0)
        self.assertAlmostEqualMoney(self._dsr(mar), 100.00)

    def test_afastamento_com_dependente_confirmado_e_recusado(self):
        emp, contract = self._contrato()
        fev = self._holerite(emp, contract, FEV, [date(2024, 2, 29)])
        mar = self._holerite(emp, contract, MAR, [date(2024, 3, 1)])
        mar.action_payslip_done()
        leave = self._afastamento(
            emp, self._tipo(), date(2024, 2, 28), date(2024, 2, 29)
        )
        with self.assertRaises(UserError):
            leave.sudo().action_validate()
        self.assertEqual(leave.state, "confirm")
        self.assertAlmostEqualMoney(self._dsr(fev), 100.00)
        self.assertAlmostEqualMoney(self._dsr(mar), 0.0)
        # Voltando o confirmado para rascunho, a validação passa.
        mar.action_payslip_draft()
        leave.sudo().action_validate()
        self.assertAlmostEqualMoney(self._dsr(mar), 100.00)

    def test_afastamento_sem_efeito_no_dsr_nao_toca_holerite_confirmado(self):
        emp, contract = self._contrato()
        mar = self._holerite(emp, contract, MAR, [date(2024, 3, 6)])
        mar.action_payslip_done()
        leave = self._afastamento(
            emp, self._tipo(), date(2024, 3, 20), date(2024, 3, 22)
        )
        leave.sudo().action_validate()
        self.assertEqual(mar.state, "done")
        self.assertAlmostEqualMoney(self._dsr(mar), 100.00)


class TestDsrFaltaTardia(PayrollCommon):
    """Falta de competência fechada, lançada no mês seguinte (data anterior)."""

    def _contrato(self):
        emp = self._create_employee()
        return emp, self._create_contract(emp, wage=3000.00)

    def _holerite(self, emp, contract, periodo, datas=(), tardias=(), faltas=None):
        slip = self._create_payslip(emp, contract, *periodo)
        linhas = [(0, 0, {"date": d}) for d in datas]
        linhas += [(0, 0, {"date": d, "tardia": True}) for d in tardias]
        slip.write(
            {
                "l10n_br_faltas_injustificadas": faltas
                if faltas is not None
                else len(linhas),
                "l10n_br_falta_ids": linhas,
            }
        )
        slip.compute_sheet()
        return slip

    def _dsr(self, slip):
        return self._get_line_total(slip, "DESC_DSR")

    def test_tardia_na_semana_ja_descontada_nao_desconta_de_novo(self):
        """Semana 29/01 a 04/02: janeiro já perdeu o repouso pela falta de 31/01."""
        emp, contract = self._contrato()
        jan = self._holerite(emp, contract, JAN, [date(2024, 1, 31)])
        jan.action_payslip_done()
        fev = self._holerite(emp, contract, FEV, tardias=[date(2024, 1, 30)])
        self.assertAlmostEqualMoney(self._dsr(jan), 100.00)
        self.assertAlmostEqualMoney(self._dsr(fev), 0.0)
        # O salário do dia faltado continua descontado no mês seguinte.
        self.assertAlmostEqualMoney(self._get_line_total(fev, "FALTAS"), 100.00)

    def test_tardia_em_semana_sem_outra_falta_desconta_o_repouso(self):
        emp, contract = self._contrato()
        jan = self._holerite(emp, contract, JAN)
        jan.action_payslip_done()
        fev = self._holerite(emp, contract, FEV, tardias=[date(2024, 1, 30)])
        self.assertAlmostEqualMoney(self._dsr(fev), 100.00)

    def test_falta_comum_posterior_na_semana_tira_o_repouso_da_tardia(self):
        emp, contract = self._contrato()
        fev = self._holerite(emp, contract, FEV, tardias=[date(2024, 1, 30)])
        self.assertAlmostEqualMoney(self._dsr(fev), 100.00)
        # Falta comum na mesma semana, no próprio mês: a semana tem dono só.
        fev.write(
            {
                "l10n_br_faltas_injustificadas": 2,
                "l10n_br_falta_ids": [(0, 0, {"date": date(2024, 2, 1)})],
            }
        )
        fev.compute_sheet()
        self.assertAlmostEqualMoney(self._dsr(fev), 100.00)

    def test_falta_sem_data_nao_cai_na_semana_ja_descontada(self):
        """Período de 01 a 04/02 toca só a semana de 29/01, que janeiro descontou."""
        emp, contract = self._contrato()
        jan = self._holerite(emp, contract, JAN, [date(2024, 1, 31)])
        jan.action_payslip_done()
        curto = self._holerite(
            emp, contract, (date(2024, 2, 1), date(2024, 2, 4)), faltas=1
        )
        self.assertAlmostEqualMoney(self._dsr(jan), 100.00)
        self.assertAlmostEqualMoney(self._dsr(curto), 0.0)

    def test_tardia_dentro_do_periodo_e_recusada(self):
        emp, contract = self._contrato()
        with self.assertRaises(ValidationError):
            self._holerite(emp, contract, FEV, tardias=[date(2024, 2, 10)])

    def test_falta_comum_antes_do_periodo_continua_recusada(self):
        emp, contract = self._contrato()
        with self.assertRaises(ValidationError):
            self._holerite(emp, contract, FEV, [date(2024, 1, 30)])
