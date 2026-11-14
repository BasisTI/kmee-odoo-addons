# Copyright 2026 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""TG-96: causas de rescisão (tabela 19 do eSocial) e as verbas de cada uma."""

from datetime import date

from odoo.exceptions import ValidationError
from odoo.tests import tagged

from odoo.addons.l10n_br_hr_vacation.models.hr_payslip import L10N_BR_REGRAS_RESCISAO

from .common import VacationCommon

SALDO_FGTS = 10000.00
INICIO = date(2024, 1, 1)
DESLIGAMENTO = date(2024, 9, 30)


@tagged("post_install", "-at_install")
class TestTiposRescisao(VacationCommon):
    """Contrato de 3000,00 desde 01/01/2024, desligado em 30/09/2024.

    Aviso de 30 dias (sem ano completo); 9 avos de 13º e de férias (10 avos
    quando o aviso indenizado projeta o contrato até 30/10).
    """

    def _rescisao(
        self,
        tipo,
        aviso="nao_aplicavel",
        inicio=INICIO,
        desligamento=DESLIGAMENTO,
        **extra
    ):
        emp = self._create_employee("Rescisão %s" % tipo)
        contract = self._create_contract(emp, wage=3000.00, date_start=inicio)
        vals = {
            "name": "Rescisão",
            "employee_id": emp.id,
            "contract_id": contract.id,
            "date_from": desligamento.replace(day=1),
            "date_to": desligamento,
            "struct_id": self.structure_rescisao.id,
            "company_id": self.env.company.id,
            "l10n_br_tipo_rescisao": tipo,
            "l10n_br_aviso_previo": aviso,
            "l10n_br_fgts_saldo_conta": SALDO_FGTS,
        }
        vals.update(extra)
        rescisao = self.env["hr.payslip"].create(vals)
        rescisao.compute_sheet()
        return rescisao

    def _g(self, rescisao, code):
        return self._get_line_total(rescisao, code)

    def _multa_esperada(self, rescisao, percentual):
        base = (
            SALDO_FGTS
            + self._g(rescisao, "FGTS")
            + self._g(rescisao, "FGTS_13")
            + self._g(rescisao, "FGTS_AVISO")
        )
        return round(base * percentual, 2)

    # ── sem justa causa e rescisão indireta ────────────────────────────

    def test_sem_justa_causa_aviso_integral_e_multa_40(self):
        r = self._rescisao("sem_justa_causa", "indenizado")
        self.assertAlmostEqualMoney(self._g(r, "AVISO_PREVIO_INDENIZADO"), 3000.00)
        self.assertAlmostEqualMoney(
            self._g(r, "MULTA_FGTS"), self._multa_esperada(r, 0.40)
        )

    def test_rescisao_indireta_igual_a_sem_justa_causa(self):
        sjc = self._rescisao("sem_justa_causa", "indenizado")
        ind = self._rescisao("rescisao_indireta", "indenizado")
        for code in (
            "AVISO_PREVIO_INDENIZADO",
            "DECIMO_RESCISAO",
            "FERIAS_INDENIZADAS",
            "ADICIONAL_FERIAS_INDENIZADAS",
            "MULTA_FGTS",
            "NET",
        ):
            self.assertAlmostEqualMoney(self._g(ind, code), self._g(sjc, code), code)
        self.assertGreater(self._g(ind, "MULTA_FGTS"), 0)

    def test_aviso_trabalhado_nao_gera_verba_de_aviso(self):
        r = self._rescisao("sem_justa_causa", "trabalhado")
        self.assertEqual(self._g(r, "AVISO_PREVIO_INDENIZADO"), 0)
        self.assertEqual(self._g(r, "FGTS_AVISO"), 0)
        # Sem projeção do aviso: 9 avos.
        self.assertAlmostEqualMoney(self._g(r, "DECIMO_RESCISAO"), 2250.00)

    # ── culpa recíproca (art. 484 CLT; Súmula 14 TST) ──────────────────

    def test_culpa_reciproca_metade_do_aviso_13_e_ferias(self):
        r = self._rescisao("culpa_reciproca", "indenizado")
        self.assertAlmostEqualMoney(self._g(r, "AVISO_PREVIO_INDENIZADO"), 1500.00)
        # 10 avos (aviso projetado) x 50%.
        self.assertAlmostEqualMoney(self._g(r, "DECIMO_RESCISAO"), 1250.00)
        self.assertAlmostEqualMoney(self._g(r, "FERIAS_INDENIZADAS"), 1250.00)
        self.assertAlmostEqualMoney(
            self._g(r, "ADICIONAL_FERIAS_INDENIZADAS"), round(1250.00 / 3, 2)
        )
        self.assertAlmostEqualMoney(
            self._g(r, "MULTA_FGTS"), self._multa_esperada(r, 0.20)
        )

    # ── força maior (art. 502 CLT) ─────────────────────────────────────

    def test_forca_maior_multa_20_sem_aviso(self):
        r = self._rescisao("forca_maior", "indenizado")
        self.assertEqual(self._g(r, "AVISO_PREVIO_INDENIZADO"), 0)
        self.assertAlmostEqualMoney(self._g(r, "DECIMO_RESCISAO"), 2250.00)
        self.assertAlmostEqualMoney(self._g(r, "FERIAS_INDENIZADAS"), 2250.00)
        self.assertAlmostEqualMoney(
            self._g(r, "MULTA_FGTS"), self._multa_esperada(r, 0.20)
        )

    # ── acordo, pedido de demissão e justa causa continuam como estavam ─

    def test_acordo_metade_do_aviso_e_multa_20(self):
        r = self._rescisao("acordo", "indenizado")
        self.assertAlmostEqualMoney(self._g(r, "AVISO_PREVIO_INDENIZADO"), 1500.00)
        self.assertAlmostEqualMoney(self._g(r, "DECIMO_RESCISAO"), 2500.00)
        self.assertAlmostEqualMoney(
            self._g(r, "MULTA_FGTS"), self._multa_esperada(r, 0.20)
        )

    def test_justa_causa_sem_13_ferias_aviso_e_multa(self):
        r = self._rescisao("justa_causa")
        for code in (
            "DECIMO_RESCISAO",
            "FERIAS_INDENIZADAS",
            "AVISO_PREVIO_INDENIZADO",
            "MULTA_FGTS",
        ):
            self.assertEqual(self._g(r, code), 0, code)

    # ── contrato a prazo ───────────────────────────────────────────────

    def test_termino_no_prazo_sem_aviso_nem_multa(self):
        r = self._rescisao("termino_contrato", "indenizado")
        for code in (
            "AVISO_PREVIO_INDENIZADO",
            "MULTA_FGTS",
            "INDENIZACAO_ART_479",
            "DESCONTO_ART_480",
        ):
            self.assertEqual(self._g(r, code), 0, code)
        self.assertAlmostEqualMoney(self._g(r, "DECIMO_RESCISAO"), 2250.00)
        self.assertAlmostEqualMoney(self._g(r, "FERIAS_INDENIZADAS"), 2250.00)

    def test_antecipado_empregador_art_479_e_multa_40(self):
        r = self._rescisao(
            "antecipado_empregador", l10n_br_data_termo_contrato=date(2024, 12, 31)
        )
        # 3 meses comerciais (90 dias) até o termo: metade de 3000/30 x 90.
        self.assertAlmostEqualMoney(self._g(r, "INDENIZACAO_ART_479"), 4500.00)
        self.assertEqual(self._g(r, "AVISO_PREVIO_INDENIZADO"), 0)
        self.assertAlmostEqualMoney(
            self._g(r, "MULTA_FGTS"), self._multa_esperada(r, 0.40)
        )
        # Indenizatória: não entra nas bases de INSS, IRRF e FGTS.
        sem = self._rescisao("termino_contrato")
        for code in ("INSS", "IRRF", "FGTS"):
            self.assertAlmostEqualMoney(self._g(r, code), self._g(sem, code), code)
        self.assertAlmostEqualMoney(self._g(r, "NET"), self._g(sem, "NET") + 4500.00)

    def test_antecipado_empregado_art_480_sem_multa(self):
        r = self._rescisao(
            "antecipado_empregado",
            l10n_br_data_termo_contrato=date(2024, 12, 31),
            l10n_br_prejuizo_art_480=500.00,
        )
        self.assertAlmostEqualMoney(self._g(r, "DESCONTO_ART_480"), 500.00)
        self.assertEqual(self._g(r, "MULTA_FGTS"), 0)
        self.assertEqual(self._g(r, "INDENIZACAO_ART_479"), 0)
        sem = self._rescisao("termino_contrato")
        self.assertAlmostEqualMoney(self._g(r, "NET"), self._g(sem, "NET") - 500.00)

    def test_antecipado_empregado_desconto_limitado_ao_art_479_e_a_um_mes(self):
        # Termo em 31/10: um mês comercial (30 dias), art. 479 = 1500,00.
        r = self._rescisao(
            "antecipado_empregado",
            l10n_br_data_termo_contrato=date(2024, 10, 31),
            l10n_br_prejuizo_art_480=9000.00,
        )
        self.assertAlmostEqualMoney(self._g(r, "DESCONTO_ART_480"), 1500.00)
        # Termo em 31/12: art. 479 = 4500,00; teto de um mês de remuneração.
        r = self._rescisao(
            "antecipado_empregado",
            l10n_br_data_termo_contrato=date(2024, 12, 31),
            l10n_br_prejuizo_art_480=9000.00,
        )
        self.assertAlmostEqualMoney(self._g(r, "DESCONTO_ART_480"), 3000.00)

    def test_antecipado_empregado_sem_prejuizo_nao_desconta(self):
        r = self._rescisao(
            "antecipado_empregado", l10n_br_data_termo_contrato=date(2024, 12, 31)
        )
        self.assertEqual(self._g(r, "DESCONTO_ART_480"), 0)

    def test_art_479_mes_de_31_dias_vale_meio_salario(self):
        # 30/09 a 31/10 é um mês: metade de 3000,00, e não 1550,00.
        r = self._rescisao(
            "antecipado_empregador", l10n_br_data_termo_contrato=date(2024, 10, 31)
        )
        self.assertAlmostEqualMoney(self._g(r, "INDENIZACAO_ART_479"), 1500.00)
        # Fevereiro: 28/02 a 31/03 também é um mês.
        r = self._rescisao(
            "antecipado_empregador",
            desligamento=date(2025, 2, 28),
            l10n_br_data_termo_contrato=date(2025, 3, 31),
        )
        self.assertAlmostEqualMoney(self._g(r, "INDENIZACAO_ART_479"), 1500.00)

    # ── descontos nunca deixam o líquido negativo ──────────────────────

    def _assert_liquido_nao_negativo(self, r, desconto, nao_descontado, devido):
        self.assertGreaterEqual(self._g(r, "NET"), 0)
        self.assertAlmostEqualMoney(self._g(r, "NET"), 0.0)
        self.assertLess(self._g(r, desconto), devido)
        # O que não coube aparece no holerite, fora do líquido.
        self.assertAlmostEqualMoney(
            self._g(r, desconto) + self._g(r, nao_descontado), devido
        )
        self.assertGreater(self._g(r, nao_descontado), 0)

    def test_aviso_nao_cumprido_limitado_ao_liquido_pouco_tempo_de_casa(self):
        r = self._rescisao(
            "pedido_demissao",
            "nao_cumprido",
            inicio=date(2024, 8, 20),
            desligamento=date(2024, 9, 5),
        )
        self._assert_liquido_nao_negativo(
            r, "DESCONTO_AVISO_PREVIO", "NAO_DESCONTADO_AVISO_PREVIO", 3000.00
        )

    def test_aviso_nao_cumprido_limitado_ao_liquido_inicio_do_ano(self):
        r = self._rescisao(
            "pedido_demissao",
            "nao_cumprido",
            inicio=date(2020, 1, 1),
            desligamento=date(2025, 1, 3),
        )
        self._assert_liquido_nao_negativo(
            r, "DESCONTO_AVISO_PREVIO", "NAO_DESCONTADO_AVISO_PREVIO", 3000.00
        )

    def test_art_480_limitado_ao_liquido(self):
        r = self._rescisao(
            "antecipado_empregado",
            inicio=date(2024, 9, 1),
            desligamento=date(2024, 9, 10),
            l10n_br_data_termo_contrato=date(2024, 11, 29),
            l10n_br_prejuizo_art_480=5000.00,
        )
        self._assert_liquido_nao_negativo(
            r, "DESCONTO_ART_480", "NAO_DESCONTADO_ART_480", 3000.00
        )

    def test_desconto_integral_quando_cabe_no_liquido(self):
        r = self._rescisao("pedido_demissao", "nao_cumprido")
        self.assertAlmostEqualMoney(self._g(r, "DESCONTO_AVISO_PREVIO"), 3000.00)
        self.assertEqual(self._g(r, "NAO_DESCONTADO_AVISO_PREVIO"), 0)

    # ── aviso não cumprido (art. 487 §2º) ──────────────────────────────

    def test_pedido_demissao_aviso_nao_cumprido_desconta_30_dias(self):
        r = self._rescisao("pedido_demissao", "nao_cumprido")
        self.assertAlmostEqualMoney(self._g(r, "DESCONTO_AVISO_PREVIO"), 3000.00)
        self.assertEqual(self._g(r, "AVISO_PREVIO_INDENIZADO"), 0)
        self.assertEqual(self._g(r, "MULTA_FGTS"), 0)
        cumprido = self._rescisao("pedido_demissao", "trabalhado")
        self.assertAlmostEqualMoney(
            self._g(r, "NET"), self._g(cumprido, "NET") - 3000.00
        )

    def test_pedido_demissao_aviso_trabalhado_nao_desconta(self):
        r = self._rescisao("pedido_demissao", "trabalhado")
        self.assertEqual(self._g(r, "DESCONTO_AVISO_PREVIO"), 0)

    # ── validações ─────────────────────────────────────────────────────

    def test_antecipado_exige_termo_posterior_ao_desligamento(self):
        for tipo in ("antecipado_empregador", "antecipado_empregado"):
            with self.assertRaises(ValidationError):
                self._rescisao(tipo)
            with self.assertRaises(ValidationError):
                self._rescisao(tipo, l10n_br_data_termo_contrato=date(2024, 9, 30))

    def test_aviso_nao_cumprido_so_no_pedido_de_demissao(self):
        with self.assertRaises(ValidationError):
            self._rescisao("sem_justa_causa", "nao_cumprido")

    def test_prejuizo_negativo_recusado(self):
        with self.assertRaises(ValidationError):
            self._rescisao(
                "antecipado_empregado",
                l10n_br_data_termo_contrato=date(2024, 12, 31),
                l10n_br_prejuizo_art_480=-1,
            )

    # ── mtvDeslig (tabela 19 do eSocial) ───────────────────────────────

    def test_motivo_desligamento_esocial_de_cada_causa(self):
        esperado = {
            "justa_causa": "01",
            "sem_justa_causa": "02",
            "antecipado_empregador": "03",
            "antecipado_empregado": "04",
            "culpa_reciproca": "05",
            "termino_contrato": "06",
            "pedido_demissao": "07",
            "rescisao_indireta": "17",
            "forca_maior": "27",
            "acordo": "33",
        }
        tipos = {
            k
            for k, _v in self.env["hr.payslip"]
            ._fields["l10n_br_tipo_rescisao"]
            .selection
        }
        self.assertEqual(tipos, set(esperado))
        # Um mtvDeslig por causa, sem repetir.
        codigos = [r["mtv"] for r in L10N_BR_REGRAS_RESCISAO.values()]
        self.assertEqual(len(codigos), len(set(codigos)))
        for tipo, codigo in esperado.items():
            slip = self.env["hr.payslip"].new({"l10n_br_tipo_rescisao": tipo})
            self.assertEqual(slip._l10n_br_motivo_desligamento_esocial(), codigo)
        self.assertFalse(
            self.env["hr.payslip"].new({})._l10n_br_motivo_desligamento_esocial()
        )
