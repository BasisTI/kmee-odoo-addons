# Copyright 2024 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""
Testes: Benefícios na Folha de Pagamento.

Cobertura:
  - Vale-Transporte com desconto máximo de 6%
  - Vale-Transporte por valor diário x dias úteis (TG-110)
  - Vale-Refeição não tributável
  - Vale-Alimentação não tributável
  - Plano de Saúde dedutível do IRRF
  - Integração benefícios × folha
"""
from datetime import date, datetime

from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase

from odoo.addons.l10n_br_hr_benefit.models.vale_transporte import (
    credito_vt,
    dias_uteis_vt,
)
from odoo.addons.l10n_br_hr_payroll.tests.common import PayrollCommon


class TestBeneficios(PayrollCommon):
    """Testes dos benefícios na folha de pagamento."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.template_vt = cls.env.ref("l10n_br_hr_benefit.advantage_template_vt")
        cls.template_vr = cls.env.ref("l10n_br_hr_benefit.advantage_template_vr")
        cls.template_va = cls.env.ref("l10n_br_hr_benefit.advantage_template_va")
        cls.template_vt_diario = cls.env.ref(
            "l10n_br_hr_benefit.advantage_template_vt_diario"
        )
        cls.template_plano = cls.env.ref(
            "l10n_br_hr_benefit.advantage_template_plano_saude"
        )

    def _add_advantage(self, contract, template, amount):
        """Helper: adiciona benefício ao contrato."""
        return self.env["hr.contract.advantage"].create(
            {
                "contract_id": contract.id,
                "advantage_template_id": template.id,
                "amount": amount,
            }
        )

    def _create_payslip_benefit(self, employee, contract):
        """Helper: cria payslip para testes de benefícios."""
        payslip = self.env["hr.payslip"].create(
            {
                "name": f"Holerite - {employee.name}",
                "employee_id": employee.id,
                "contract_id": contract.id,
                "struct_id": contract.struct_id.id,
                "date_from": date(2024, 3, 1),
                "date_to": date(2024, 3, 31),
                "company_id": self.env.company.id,
            }
        )
        payslip.compute_sheet()
        return payslip

    # ── Vale-Transporte ─────────────────────────────────────────

    def test_vt_desconto_menor_que_6_porcento(self):
        """VT menor que 6% do salário: desconta o valor integral."""
        emp = self._create_employee()
        contract = self._create_contract(emp, wage=5000.00)
        self._add_advantage(contract, self.template_vt, 100.00)
        payslip = self._create_payslip_benefit(emp, contract)
        desc_vt = self._get_line_total(payslip, "DESC_VT")
        # 6% de 5000 = 300. VT = 100 < 300 → desconta 100
        self.assertAlmostEqualMoney(desc_vt, 100.00)

    def test_vt_desconto_limitado_a_6_porcento(self):
        """VT maior que 6% do salário: desconta apenas 6%."""
        emp = self._create_employee()
        contract = self._create_contract(emp, wage=2000.00)
        self._add_advantage(contract, self.template_vt, 200.00)
        payslip = self._create_payslip_benefit(emp, contract)
        desc_vt = self._get_line_total(payslip, "DESC_VT")
        # 6% de 2000 = 120. VT = 200 > 120 → desconta 120
        self.assertAlmostEqualMoney(desc_vt, 120.00)

    def test_vt_exatamente_6_porcento(self):
        """VT igual a 6%: desconta tudo."""
        emp = self._create_employee()
        contract = self._create_contract(emp, wage=3000.00)
        self._add_advantage(contract, self.template_vt, 180.00)
        payslip = self._create_payslip_benefit(emp, contract)
        desc_vt = self._get_line_total(payslip, "DESC_VT")
        # 6% de 3000 = 180. VT = 180 → desconta 180
        self.assertAlmostEqualMoney(desc_vt, 180.00)

    def test_vt_zero_sem_desconto(self):
        """Sem VT configurado: nenhum desconto."""
        emp = self._create_employee()
        contract = self._create_contract(emp, wage=5000.00)
        payslip = self._create_payslip_benefit(emp, contract)
        desc_vt = self._get_line_total(payslip, "DESC_VT")
        self.assertEqual(desc_vt, 0.0)

    # ── Vale-Refeição ───────────────────────────────────────────

    def test_vr_informativo_nao_tributavel(self):
        """VR aparece como informativo e não compõe base do INSS."""
        emp = self._create_employee()
        contract = self._create_contract(emp, wage=3000.00)
        self._add_advantage(contract, self.template_vr, 800.00)
        payslip = self._create_payslip_benefit(emp, contract)
        vr = self._get_line_total(payslip, "VR_INFO")
        self.assertAlmostEqualMoney(vr, 800.00)
        # INSS deve ser calculado sobre o salário, não sobre salário + VR
        inss_com_vr = self._get_line_total(payslip, "INSS")
        # Recalcula sem VR para comparar
        emp2 = self._create_employee(name="Sem VR")
        contract2 = self._create_contract(emp2, wage=3000.00)
        payslip2 = self._create_payslip_benefit(emp2, contract2)
        inss_sem_vr = self._get_line_total(payslip2, "INSS")
        self.assertAlmostEqualMoney(inss_com_vr, inss_sem_vr)

    # ── Vale-Alimentação ────────────────────────────────────────

    def test_va_informativo(self):
        """VA aparece como informativo."""
        emp = self._create_employee()
        contract = self._create_contract(emp, wage=3000.00)
        self._add_advantage(contract, self.template_va, 600.00)
        payslip = self._create_payslip_benefit(emp, contract)
        va = self._get_line_total(payslip, "VA_INFO")
        self.assertAlmostEqualMoney(va, 600.00)

    # ── Plano de Saúde ──────────────────────────────────────────

    def test_plano_saude_desconta_do_salario(self):
        """Coparticipação do plano de saúde é descontada do salário."""
        emp = self._create_employee()
        contract = self._create_contract(emp, wage=5000.00)
        self._add_advantage(contract, self.template_plano, 150.00)
        payslip = self._create_payslip_benefit(emp, contract)
        desc = self._get_line_total(payslip, "DESC_PLANO_SAUDE")
        self.assertAlmostEqualMoney(desc, 150.00)

    def test_plano_saude_nao_altera_base_irrf(self):
        """Plano de saúde NÃO altera a base do IRRF na retenção mensal.

        Fisco (Fix 1): a coparticipação/mensalidade de plano de saúde não é
        dedutível na retenção do IRRF na fonte — só é dedutível na Declaração
        de Ajuste Anual (art. 4º Lei 9.250/95; art. 677 RIR/2018; art. 52 IN
        RFB 1.500/2014). O desconto DESC_PLANO_SAUDE reduz o líquido (categoria
        DED), mas a BASE_IRRF permanece a mesma. O override que reduzia a base
        foi removido em data/hr_payroll_structure_data.xml.
        """
        emp = self._create_employee()
        contract = self._create_contract(emp, wage=5000.00)
        # Sem plano
        payslip_sem = self._create_payslip_benefit(emp, contract)
        irrf_sem = self._get_line_total(payslip_sem, "IRRF")
        # Com plano
        self._add_advantage(contract, self.template_plano, 500.00)
        payslip_com = self._create_payslip_benefit(emp, contract)
        irrf_com = self._get_line_total(payslip_com, "IRRF")
        # IRRF deve ser IGUAL com e sem plano (base inalterada).
        self.assertAlmostEqualMoney(
            irrf_com,
            irrf_sem,
            msg="Plano de saúde não pode alterar a base/IRRF na fonte",
        )

    # ── Integração ──────────────────────────────────────────────

    def test_beneficios_nao_alteram_gross(self):
        """Benefícios INFO não alteram o GROSS."""
        emp = self._create_employee()
        contract = self._create_contract(emp, wage=5000.00)
        self._add_advantage(contract, self.template_vr, 800.00)
        self._add_advantage(contract, self.template_va, 600.00)
        payslip = self._create_payslip_benefit(emp, contract)
        gross = self._get_line_total(payslip, "GROSS")
        self.assertAlmostEqualMoney(gross, 5000.00)

    def test_beneficios_ded_reduzem_net(self):
        """Benefícios DED reduzem o líquido."""
        emp = self._create_employee()
        contract = self._create_contract(emp, wage=5000.00)
        # Folha sem benefícios
        payslip_sem = self._create_payslip_benefit(emp, contract)
        net_sem = self._get_line_total(payslip_sem, "NET")
        # Folha com VT + plano
        self._add_advantage(contract, self.template_vt, 200.00)
        self._add_advantage(contract, self.template_plano, 150.00)
        payslip_com = self._create_payslip_benefit(emp, contract)
        net_com = self._get_line_total(payslip_com, "NET")
        self.assertLess(net_com, net_sem)


class TestValeTransporteDiario(PayrollCommon):
    """VT pelo valor diário da tarifa x dias úteis do mês (TG-110).

    Março de 2024: 31 dias, 21 de segunda a sexta e 5 sábados.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.template_vt = cls.env.ref("l10n_br_hr_benefit.advantage_template_vt")
        cls.template_vt_diario = cls.env.ref(
            "l10n_br_hr_benefit.advantage_template_vt_diario"
        )
        cls.env.user.tz = "UTC"
        cls.env.company.partner_id.tz = "UTC"
        cls.calendario = cls.env["resource.calendar"].create(
            {"name": "Escala 5x2 (VT)", "tz": "UTC"}
        )
        # Feriados de outros módulos instalados no banco não contam no teste.
        cls.env["resource.calendar.leaves"].sudo().search(
            [
                ("resource_id", "=", False),
                ("date_from", "<", datetime(2024, 4, 3)),
                ("date_to", ">", datetime(2024, 2, 27)),
            ]
        ).unlink()

    def _add_advantage(self, contract, template, amount):
        return self.env["hr.contract.advantage"].create(
            {
                "contract_id": contract.id,
                "advantage_template_id": template.id,
                "amount": amount,
            }
        )

    def _create_payslip_benefit(self, employee, contract):
        return self._create_payslip(employee, contract)

    def _contrato(self, wage, diario, calendario=None, date_start=None):
        emp = self._create_employee()
        contract = self._create_contract(emp, wage=wage, date_start=date_start)
        contract.resource_calendar_id = calendario or self.calendario
        self._add_advantage(contract, self.template_vt_diario, diario)
        return emp, contract

    def _feriado(self, dia):
        return self.env["resource.calendar.leaves"].create(
            {
                "name": "Feriado (teste)",
                "calendar_id": self.calendario.id,
                "company_id": self.env.company.id,
                "date_from": datetime(dia.year, dia.month, dia.day, 0, 0, 0),
                "date_to": datetime(dia.year, dia.month, dia.day, 23, 59, 59),
            }
        )

    def test_credito_e_desconto_pelo_valor_diario(self):
        """Crédito = diário x 21 dias úteis; o desconto é 6% do salário."""
        emp, contract = self._contrato(wage=2000.0, diario=10.0)
        payslip = self._create_payslip_benefit(emp, contract)
        self.assertAlmostEqualMoney(self._get_line_total(payslip, "VT_INFO"), 210.0)
        # 6% de 2000 = 120 < 210: o desconto é o limite de 6%
        self.assertAlmostEqualMoney(self._get_line_total(payslip, "DESC_VT"), 120.0)

    def test_desconto_limitado_ao_custo_por_dias_uteis(self):
        """Custo menor que 6%: desconta só o custo dos dias úteis."""
        emp, contract = self._contrato(wage=5000.0, diario=10.0)
        payslip = self._create_payslip_benefit(emp, contract)
        # 6% de 5000 = 300 > 210 (10 x 21): desconta o custo
        self.assertAlmostEqualMoney(self._get_line_total(payslip, "DESC_VT"), 210.0)

    def test_feriado_sai_dos_dias_uteis(self):
        emp, contract = self._contrato(wage=5000.0, diario=10.0)
        self._feriado(date(2024, 3, 29))
        payslip = self._create_payslip_benefit(emp, contract)
        self.assertAlmostEqualMoney(self._get_line_total(payslip, "VT_INFO"), 200.0)
        self.assertAlmostEqualMoney(self._get_line_total(payslip, "DESC_VT"), 200.0)

    def test_escala_seis_por_um_conta_o_sabado(self):
        calendario = self.calendario.copy({"name": "Escala 6x1 (VT)"})
        calendario.write(
            {
                "attendance_ids": [
                    (
                        0,
                        0,
                        {
                            "name": "Sábado",
                            "dayofweek": "5",
                            "hour_from": 8,
                            "hour_to": 12,
                        },
                    )
                ]
            }
        )
        emp, contract = self._contrato(wage=5000.0, diario=10.0, calendario=calendario)
        payslip = self._create_payslip_benefit(emp, contract)
        # 21 dias de segunda a sexta + 5 sábados
        self.assertAlmostEqualMoney(self._get_line_total(payslip, "VT_INFO"), 260.0)

    def test_admissao_no_meio_do_mes_conta_so_a_vigencia(self):
        emp, contract = self._contrato(
            wage=3000.0, diario=10.0, date_start=date(2024, 3, 15)
        )
        payslip = self._create_payslip_benefit(emp, contract)
        # 15, 18 a 22 e 25 a 29: 11 dias úteis
        self.assertAlmostEqualMoney(self._get_line_total(payslip, "VT_INFO"), 110.0)
        # 6% do salário proporcional: 3000 x 17/30 x 6% = 102
        self.assertAlmostEqualMoney(self._get_line_total(payslip, "DESC_VT"), 102.0)

    def test_afastamento_aprovado_sai_dos_dias_uteis(self):
        tipo = self.env["hr.leave.type"].create(
            {
                "name": "Licença (teste VT)",
                "requires_allocation": "no",
                "leave_validation_type": "no_validation",
            }
        )
        emp, contract = self._contrato(wage=5000.0, diario=10.0)
        leave = self.env["hr.leave"].create(
            {
                "employee_id": emp.id,
                "holiday_status_id": tipo.id,
                "request_date_from": date(2024, 3, 11),
                "request_date_to": date(2024, 3, 15),
            }
        )
        if leave.state != "validate":
            leave.sudo().action_validate()
        payslip = self._create_payslip_benefit(emp, contract)
        # 21 dias úteis menos a semana de 11 a 15
        self.assertAlmostEqualMoney(self._get_line_total(payslip, "VT_INFO"), 160.0)

    def test_vt_mensal_antigo_segue_valendo_sem_valor_diario(self):
        emp = self._create_employee()
        contract = self._create_contract(emp, wage=5000.0)
        self._add_advantage(contract, self.template_vt, 100.0)
        payslip = self._create_payslip_benefit(emp, contract)
        self.assertAlmostEqualMoney(self._get_line_total(payslip, "VT_INFO"), 100.0)
        self.assertAlmostEqualMoney(self._get_line_total(payslip, "DESC_VT"), 100.0)

    def test_renuncia_ao_vt_sem_credito_nem_desconto(self):
        emp, contract = self._contrato(wage=5000.0, diario=10.0)
        contract.advantages_ids.unlink()
        payslip = self._create_payslip_benefit(emp, contract)
        self.assertEqual(self._get_line_total(payslip, "VT_INFO"), 0.0)
        self.assertEqual(self._get_line_total(payslip, "DESC_VT"), 0.0)

    def test_salario_com_variaveis_desconta_6_porcento_so_do_salario_base(self):
        emp, contract = self._contrato(wage=2000.0, diario=50.0)
        payslip = self._create_payslip_benefit(emp, contract)
        # crédito 1050; 6% só do salário-base (2000) = 120, nunca do bruto
        self.assertAlmostEqualMoney(self._get_line_total(payslip, "DESC_VT"), 120.0)

    def test_holerite_aberto_recalcula_ao_mudar_o_valor_diario(self):
        emp, contract = self._contrato(wage=5000.0, diario=10.0)
        payslip = self._create_payslip_benefit(emp, contract)
        self.assertAlmostEqualMoney(self._get_line_total(payslip, "VT_INFO"), 210.0)
        contract.advantages_ids.filtered(
            lambda a: a.advantage_template_code == "VT_DIARIO"
        ).amount = 12.0
        self.assertAlmostEqualMoney(self._get_line_total(payslip, "VT_INFO"), 252.0)

    def test_holerite_confirmado_da_competencia_vigente_recusa_a_mudanca(self):
        emp, contract = self._contrato(wage=5000.0, diario=10.0)
        hoje = date.today()
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
        payslip.action_payslip_done()
        with self.assertRaises(UserError):
            contract.advantages_ids.amount = 12.0

    def test_holerite_confirmado_de_competencia_encerrada_nao_muda(self):
        emp, contract = self._contrato(wage=5000.0, diario=10.0)
        payslip = self._create_payslip_benefit(emp, contract)
        payslip.action_payslip_done()
        contract.advantages_ids.amount = 12.0
        self.assertAlmostEqualMoney(self._get_line_total(payslip, "VT_INFO"), 210.0)


class TestDiasUteisVT(TransactionCase):
    """Contagem pura dos dias úteis do VT."""

    SEG_A_SEX = {0, 1, 2, 3, 4}

    def test_mes_inteiro(self):
        self.assertEqual(
            dias_uteis_vt(date(2024, 3, 1), date(2024, 3, 31), self.SEG_A_SEX), 21
        )

    def test_feriado_em_fim_de_semana_nao_altera(self):
        self.assertEqual(
            dias_uteis_vt(
                date(2024, 3, 1),
                date(2024, 3, 31),
                self.SEG_A_SEX,
                feriados={date(2024, 3, 30)},
            ),
            21,
        )

    def test_ausencias_sobrepostas_descontam_cada_dia_uma_vez(self):
        self.assertEqual(
            dias_uteis_vt(
                date(2024, 3, 1),
                date(2024, 3, 31),
                self.SEG_A_SEX,
                ausencias=[
                    (date(2024, 3, 11), date(2024, 3, 13)),
                    (date(2024, 3, 12), date(2024, 3, 14)),
                ],
            ),
            17,
        )

    def test_janela_vazia(self):
        self.assertEqual(
            dias_uteis_vt(date(2024, 3, 20), date(2024, 3, 10), self.SEG_A_SEX), 0
        )

    def test_credito_arredondado_em_centavos(self):
        self.assertEqual(credito_vt(3.333, 21), 69.99)
