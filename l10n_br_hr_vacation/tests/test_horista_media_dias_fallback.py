# Copyright 2026 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""TG-168 r2: média do horista pesada pelos dias e fallback pelo mensal da competência.

Decisões TG-168#P1 e #P2: a média pesa cada mensal por dias de salário ÷ 30; sem
mensal confirmado na janela, valem as horas do mensal do mesmo contrato e da mesma
competência, levadas a 30 dias; sem ele, o mensal de referência. O recibo de
férias, de 13º ou de rescisão nunca é a fonte das horas.
"""

from datetime import date

from dateutil.relativedelta import relativedelta

from odoo.tests import tagged

from odoo.addons.l10n_br_hr_payroll.models.salary_rules_br import round_money

from .common import VacationCommon

VH = 20.0


@tagged("post_install", "-at_install")
class TestHoristaMediaDiasFallback(VacationCommon):
    def _horista(self, nome, date_start=None):
        emp = self._create_employee(nome)
        contract = self._create_contract(
            emp, wage=3500.0, date_start=date_start or date(2024, 1, 1)
        )
        contract.write(
            {"salary_unit": self._unidade_salario("1").id, "l10n_br_valor_hora": VH}
        )
        return emp, contract

    def _mensal(self, emp, contract, ano, mes, horas, confirmar=True):
        slip = self.env["hr.payslip"].create(
            {
                "name": f"Mensal {mes}/{ano}",
                "employee_id": emp.id,
                "contract_id": contract.id,
                "struct_id": self.structure_clt.id,
                "date_from": date(ano, mes, 1),
                "date_to": date(ano, mes, 1) + relativedelta(day=31),
                "l10n_br_horas_pagas": horas,
                "company_id": self.env.company.id,
            }
        )
        slip.compute_sheet()
        if confirmar:
            slip.action_payslip_done()
        return slip

    def _rem(self, slip):
        return self._get_line_total(slip, "SALARIO_BASE") + self._get_line_total(
            slip, "DSR_HORISTA"
        )

    def _alocacao(self, emp, inicio, fim):
        alocacao = self.env["hr.leave.allocation"].create(
            {
                "employee_id": emp.id,
                "holiday_status_id": self.leave_type_ferias.id,
                "date_from": inicio,
                "date_to": fim,
            }
        )
        alocacao.action_validate()
        return alocacao

    def _recibo(self, emp, contract, inicio, fim, dias, alocacao):
        return self.env["hr.payslip"].create(
            {
                "name": f"Férias {inicio}",
                "employee_id": emp.id,
                "contract_id": contract.id,
                "struct_id": self.structure_ferias.id,
                "date_from": inicio,
                "date_to": fim,
                "l10n_br_ferias_allocation_id": alocacao.id,
                "l10n_br_dias_periodo_gozado": dias,
                "company_id": self.env.company.id,
            }
        )

    def _slip(self, emp, contract, estrutura, inicio, fim, **extra):
        slip = self.env["hr.payslip"].create(
            dict(
                {
                    "name": "Verba",
                    "employee_id": emp.id,
                    "contract_id": contract.id,
                    "struct_id": estrutura.id,
                    "date_from": inicio,
                    "date_to": fim,
                    "company_id": self.env.company.id,
                },
                **extra,
            )
        )
        slip.compute_sheet()
        return slip

    def test_ferias_parciais_nao_mudam_o_13(self):
        """Férias de 30 dias iniciadas em dias diferentes dão o mesmo 13º."""
        brutos = {}
        for nome, inicio, fim, horas_mes in (
            ("A", date(2024, 6, 1), date(2024, 6, 30), {}),
            ("B", date(2024, 6, 16), date(2024, 7, 15), {6: 80.0, 7: 85.33}),
        ):
            emp, contract = self._horista("Média " + nome)
            alocacao = self._alocacao(emp, date(2023, 1, 1), date(2023, 12, 31))
            self._recibo(emp, contract, inicio, fim, 30, alocacao)
            for mes in range(1, 12):
                if nome == "A" and mes == 6:
                    continue
                self._mensal(emp, contract, 2024, mes, horas_mes.get(mes, 160.0))
            dec = self._slip(
                emp, contract, self.structure_13, date(2024, 12, 1), date(2024, 12, 31)
            )
            brutos[nome] = self._get_line_total(dec, "DECIMO_TERCEIRO_BRUTO")
        # O repouso varia com os dias úteis de cada mês: até 1% de diferença.
        self.assertAlmostEqual(
            brutos["A"], brutos["B"], delta=brutos["A"] * 0.01, msg=str(brutos)
        )

    def test_admissao_no_meio_do_mes_nao_puxa_a_media(self):
        emp, contract = self._horista("Média adm", date_start=date(2024, 3, 20))
        for mes in range(3, 12):
            self._mensal(emp, contract, 2024, mes, 56.0 if mes == 3 else 160.0)
        abril = self._rem(
            self.env["hr.payslip"].search(
                [("contract_id", "=", contract.id), ("date_from", "=", "2024-04-01")]
            )
        )
        dec = self._slip(
            emp, contract, self.structure_13, date(2024, 12, 1), date(2024, 12, 31)
        )
        referencia = dec._l10n_br_salario_referencia(contract, "13")
        self.assertAlmostEqual(referencia, abril, delta=abril * 0.015)

    def test_fallback_ferias_fracionadas_mesma_base(self):
        """Sem histórico: férias de 10 e de 20 dias têm a mesma base; 1 : 2."""
        folhas = {}
        for dias in (10, 20):
            emp, contract = self._horista(f"Fallback {dias}")
            alocacao = self._alocacao(emp, date(2024, 1, 1), date(2024, 12, 31))
            recibo = self._recibo(
                emp,
                contract,
                date(2025, 2, 3),
                date(2025, 2, 3) + relativedelta(days=dias - 1),
                dias,
                alocacao,
            )
            mensal = self._mensal(emp, contract, 2025, 2, 160.0, confirmar=False)
            # As horas pagas não incluem os dias de férias (como no mensal real).
            dias_salario = recibo._l10n_br_dias_salario_do_mensal(mensal, contract)
            mensal.l10n_br_horas_pagas = 8.0 * dias_salario
            mensal.compute_sheet()
            recibo.compute_sheet()
            folhas[dias] = (
                recibo._l10n_br_salario_referencia(contract, "ferias"),
                self._get_line_total(recibo, "FERIAS"),
            )
        self.assertAlmostEqual(folhas[10][0], folhas[20][0], delta=1.0)
        self.assertAlmostEqual(folhas[10][1] * 2, folhas[20][1], delta=0.05)

    def test_recibo_nunca_e_fonte_das_horas(self):
        """Sem mensal da competência o recibo cai no mensal de referência."""
        emp, contract = self._horista("Sem mensal")
        alocacao = self._alocacao(emp, date(2024, 1, 1), date(2024, 12, 31))
        recibo = self._recibo(
            emp, contract, date(2025, 2, 3), date(2025, 2, 12), 10, alocacao
        )
        recibo.compute_sheet()
        self.assertTrue(recibo._l10n_br_horas_do_horista())
        self.assertEqual(
            recibo._l10n_br_salario_referencia(contract, "ferias"), contract.wage
        )

    def test_primeira_parcela_13_sem_historico_pelo_mensal_da_competencia(self):
        bases = {}
        for horas in (0.0, 152.0):
            emp, contract = self._horista(f"13 sem histórico {horas}")
            mensal = self._mensal(emp, contract, 2025, 11, horas, confirmar=False)
            primeira = self._slip(
                emp,
                contract,
                self.structure_13_primeira,
                date(2025, 11, 1),
                date(2025, 11, 30),
            )
            # Horas pagas vazias valem as do calendário; o mensal manda, não o
            # recibo do 13º.
            esperado = round_money(
                mensal._l10n_br_horas_do_horista() * VH + mensal._l10n_br_dsr_horista()
            )
            bases[horas] = (
                primeira._l10n_br_salario_referencia(contract, "13"),
                self._get_line_total(primeira, "ADIANTAMENTO_13"),
                esperado,
            )
        for horas in (0.0, 152.0):
            self.assertEqual(bases[horas][0], bases[horas][2])
        self.assertNotEqual(bases[0.0][1], bases[152.0][1])

    def test_rescisao_usa_a_media_de_12_meses_nao_as_horas_dos_dias(self):
        emp, contract = self._horista("Rescisão 12m", date_start=date(2024, 4, 15))
        for i in range(13):
            data = date(2024, 4, 1) + relativedelta(months=i)
            self._mensal(emp, contract, data.year, data.month, 160.0)
        rescisao = self._slip(
            emp,
            contract,
            self.structure_rescisao,
            date(2025, 5, 1),
            date(2025, 5, 20),
            l10n_br_horas_pagas=112.0,
        )
        proporcionais = rescisao._l10n_br_salario_referencia(
            contract, "ferias_proporcionais"
        )
        self.assertEqual(
            proporcionais, rescisao._l10n_br_salario_referencia(contract, "momento")
        )
        self.assertGreater(proporcionais, 3500.0)

    def test_parcial_desligado_no_primeiro_mes_nao_recebe_a_mais(self):
        calendario = self.env["resource.calendar"].create(
            {
                "name": "20h semanais 168r2",
                "attendance_ids": [
                    (
                        0,
                        0,
                        {
                            "name": nome,
                            "dayofweek": str(i),
                            "hour_from": 8,
                            "hour_to": 12,
                        },
                    )
                    for i, nome in enumerate(("seg", "ter", "qua", "qui", "sex"))
                ],
            }
        )
        emp, contract = self._horista("Parcial r2", date_start=date(2024, 9, 1))
        contract.resource_calendar_id = calendario
        self._mensal(emp, contract, 2024, 9, 60.0, confirmar=False)
        rescisao = self._slip(
            emp,
            contract,
            self.structure_rescisao,
            date(2024, 9, 1),
            date(2024, 9, 30),
            l10n_br_horas_pagas=60.0,
        )
        referencia = rescisao._l10n_br_salario_referencia(
            contract, "ferias_proporcionais"
        )
        self.assertLess(referencia, contract.wage)
        self.assertGreater(referencia, 0)
