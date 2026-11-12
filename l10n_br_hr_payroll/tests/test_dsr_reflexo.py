# Copyright 2024 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""TG-86: horas extras e adicional noturno refletem no DSR (Súmulas 172 e 60)."""

import importlib.util
from datetime import date, datetime, timedelta

import pytz

from odoo.tests.common import TransactionCase
from odoo.tools import file_path

from odoo.addons.l10n_br_hr_payroll.models.salary_rules_br import (
    calc_dsr_reflexo,
    dia_feriado_da_ausencia,
    dias_dsr,
)

from .common import PayrollCommon

OUT_2026 = dict(date_from=date(2026, 10, 1), date_to=date(2026, 10, 31))
FERIADO = date(2026, 10, 12)


class TestDiasDsrPuro(TransactionCase):
    """Dias úteis e de repouso do mês."""

    def test_so_domingos(self):
        # Outubro/2026: 31 dias, domingos 4, 11, 18 e 25.
        self.assertEqual(dias_dsr(2026, 10), (27, 4))

    def test_feriado_vira_repouso(self):
        self.assertEqual(dias_dsr(2026, 10, {FERIADO}), (26, 5))

    def test_feriado_no_domingo_nao_conta_duas_vezes(self):
        self.assertEqual(dias_dsr(2026, 10, {date(2026, 10, 4)}), (27, 4))

    def test_feriado_de_outro_mes_e_ignorado(self):
        self.assertEqual(dias_dsr(2026, 10, {date(2026, 11, 2)}), (27, 4))

    def test_reflexo(self):
        # P022 do gabarito: 360,00 de horas extras, 26 úteis, 5 repousos.
        self.assertEqual(calc_dsr_reflexo(360.0, 26, 5), 69.23)
        self.assertEqual(calc_dsr_reflexo(160.0, 26, 5), 30.77)

    def test_reflexo_sem_valor_ou_sem_dia_util(self):
        self.assertEqual(calc_dsr_reflexo(0.0, 26, 5), 0.0)
        self.assertEqual(calc_dsr_reflexo(100.0, 0, 5), 0.0)


class TestFeriadoDaAusenciaPuro(TransactionCase):
    """Que ausência global é feriado (hora local do calendário)."""

    DIA = date(2026, 10, 12)

    def _hora(self, dia, h, m=0, s=0):
        return datetime(dia.year, dia.month, dia.day, h, m, s)

    def _janela(self, dia):
        return 8.0, 17.0

    def test_dia_inteiro(self):
        self.assertEqual(
            dia_feriado_da_ausencia(
                self._hora(self.DIA, 0), self._hora(self.DIA, 23, 59, 59)
            ),
            self.DIA,
        )

    def test_fim_a_meia_noite_nao_toca_o_dia_seguinte(self):
        seguinte = self.DIA + timedelta(days=1)
        self.assertEqual(
            dia_feriado_da_ausencia(self._hora(self.DIA, 0), self._hora(seguinte, 0)),
            self.DIA,
        )

    def test_sobra_no_dia_seguinte_nao_o_torna_feriado(self):
        seguinte = self.DIA + timedelta(days=1)
        self.assertEqual(
            dia_feriado_da_ausencia(
                self._hora(self.DIA, 0), self._hora(seguinte, 1, 59, 59), self._janela
            ),
            self.DIA,
        )

    def test_meio_expediente_nao_e_feriado(self):
        self.assertIsNone(
            dia_feriado_da_ausencia(
                self._hora(self.DIA, 8), self._hora(self.DIA, 12), self._janela
            )
        )

    def test_expediente_inteiro_basta(self):
        self.assertEqual(
            dia_feriado_da_ausencia(
                self._hora(self.DIA, 8), self._hora(self.DIA, 17), self._janela
            ),
            self.DIA,
        )

    def test_recesso_de_varios_dias_nao_e_feriado(self):
        self.assertIsNone(
            dia_feriado_da_ausencia(
                self._hora(date(2026, 12, 21), 0), self._hora(date(2026, 12, 31), 23)
            )
        )

    def test_intervalo_invertido(self):
        self.assertIsNone(
            dia_feriado_da_ausencia(self._hora(self.DIA, 12), self._hora(self.DIA, 8))
        )


class BaseDsrReflexo(PayrollCommon):
    """Fixtures: calendário, feriado e holerite de 10/2026."""

    def setUp(self):
        super().setUp()
        # O fuso do usuário muda onde o hr_holidays grava a ausência com
        # calendário, e o do CI não é o da máquina local: todo teste parte de
        # um fuso explícito (UTC) e quem precisa de outro o diz (tz_usuario).
        self.env.user.tz = "UTC"
        # Outros módulos instalados no mesmo banco (CI do repositório) trazem
        # feriados globais; o teste precisa contar só os que ele cria.
        self.env["resource.calendar.leaves"].sudo().search(
            [
                ("resource_id", "=", False),
                ("date_from", "<", datetime(2026, 11, 2)),
                ("date_to", ">", datetime(2026, 9, 29)),
            ]
        ).unlink()

    def _calendario(self, tz="America/Sao_Paulo"):
        return self.env["resource.calendar"].create(
            {"name": "Calendário DSR", "tz": tz}
        )

    def _feriado(self, calendario, dia=FERIADO, empresa=None, tz_usuario=None, **extra):
        """Feriado lançado como na tela: dia inteiro na hora do usuário.

        O navegador manda 00:00 e 23:59:59 do dia no fuso do usuário, em UTC;
        com calendário, o ``hr_holidays`` reescreve para o fuso do calendário.
        O resultado tem de ser o mesmo qualquer que seja o fuso de quem lança.
        """
        fuso = pytz.timezone(tz_usuario or "America/Sao_Paulo")
        self.env.user.tz = fuso.zone

        def utc(hora, minuto, segundo):
            local = fuso.localize(
                datetime(dia.year, dia.month, dia.day, hora, minuto, segundo)
            )
            return local.astimezone(pytz.utc).replace(tzinfo=None)

        return self._ausencia(
            calendario, utc(0, 0, 0), utc(23, 59, 59), empresa=empresa, **extra
        )

    def _ausencia(
        self, calendario, inicio, fim, empresa=None, tz_usuario=None, **extra
    ):
        """Ausência global com os instantes UTC dados.

        O fuso do usuário é sempre explícito (``tz_usuario``; sem ele, o do
        calendário, que não desloca nada): o ``hr_holidays`` regrava a
        ausência com calendário pelo fuso de quem a cria.
        """
        self.env.user.tz = tz_usuario or (calendario and calendario.tz) or "UTC"
        vals = {
            "name": "Feriado",
            "calendar_id": calendario.id if calendario else False,
            "company_id": (empresa or self.env.company).id,
            "date_from": inicio,
            "date_to": fim,
        }
        vals.update(extra)
        return self.env["resource.calendar.leaves"].create(vals)

    def _ausencia_local(self, calendario, dia, hora_ini, hora_fim, tz_usuario):
        """Ausência como o usuário a digita: a hora de parede, no PRÓPRIO fuso.

        ``hora_ini``/``hora_fim`` são horas decimais do dia (``fim`` pode passar
        de 24). O navegador manda o instante UTC dessa hora no fuso do usuário
        e o ``hr_holidays`` o leva para o fuso do calendário.
        """
        fuso = pytz.timezone(tz_usuario)

        def utc(horas):
            local = datetime(dia.year, dia.month, dia.day) + timedelta(hours=horas)
            return fuso.localize(local).astimezone(pytz.utc).replace(tzinfo=None)

        return self._ausencia(
            calendario, utc(hora_ini), utc(hora_fim), tz_usuario=tz_usuario
        )

    def _holerite(self, calendario=None, **campos):
        emp = self._create_employee()
        contract = self._create_contract(emp, wage=3500.00)
        if calendario:
            contract.resource_calendar_id = calendario
        slip = self._create_payslip(emp, contract, **OUT_2026)
        slip.write(campos)
        slip.compute_sheet()
        return slip


class TestDsrReflexoHolerite(BaseDsrReflexo):
    """Holerite mensal: DSR_HE e DSR_NOTURNO a partir das verbas do mês."""

    def test_dsr_sobre_horas_extras_com_feriado(self):
        cal = self._calendario()
        self._feriado(cal)
        slip = self._holerite(cal, l10n_br_horas_extras_50=10.0)
        he = self._get_line_total(slip, "HE_50")
        self.assertGreater(he, 0)
        self.assertAlmostEqualMoney(
            self._get_line_total(slip, "DSR_HE"), round(he / 26 * 5, 2)
        )

    def test_sem_feriado_so_domingos(self):
        cal = self._calendario()
        slip = self._holerite(cal, l10n_br_horas_extras_50=10.0)
        he = self._get_line_total(slip, "HE_50")
        self.assertAlmostEqualMoney(
            self._get_line_total(slip, "DSR_HE"), round(he / 27 * 4, 2)
        )

    def test_dsr_sobre_adicional_noturno(self):
        cal = self._calendario()
        self._feriado(cal)
        slip = self._holerite(
            cal, l10n_br_horas_noturnas=40.0, l10n_br_usar_hora_reduzida=True
        )
        noturno = self._get_line_total(slip, "ADICIONAL_NOTURNO")
        self.assertGreater(noturno, 0)
        self.assertAlmostEqualMoney(
            self._get_line_total(slip, "DSR_NOTURNO"), round(noturno / 26 * 5, 2)
        )
        self.assertFalse(slip.line_ids.filtered(lambda ln: ln.code == "DSR_HE"))

    def test_reflexo_entra_no_bruto_e_nas_bases(self):
        cal = self._calendario()
        self._feriado(cal)
        slip = self._holerite(
            cal, l10n_br_horas_extras_50=10.0, l10n_br_horas_noturnas=40.0
        )
        dsr = self._get_line_total(slip, "DSR_HE") + self._get_line_total(
            slip, "DSR_NOTURNO"
        )
        sem = (
            3500.00
            + self._get_line_total(slip, "HE_50")
            + self._get_line_total(slip, "ADICIONAL_NOTURNO")
        )
        self.assertAlmostEqualMoney(self._get_line_total(slip, "GROSS"), sem + dsr)
        # FGTS = 8% da base, que inclui o reflexo.
        self.assertAlmostEqualMoney(
            self._get_line_total(slip, "FGTS"), round((sem + dsr) * 0.08, 2)
        )

    def test_sem_horas_nao_gera_reflexo(self):
        slip = self._holerite()
        codes = slip.line_ids.mapped("code")
        self.assertNotIn("DSR_HE", codes)
        self.assertNotIn("DSR_NOTURNO", codes)

    def test_feriado_de_outro_calendario_ou_empresa_nao_conta(self):
        cal = self._calendario()
        outro = self._calendario()
        self._feriado(outro)
        empresa = self.env["res.company"].create({"name": "Outra empresa DSR"})
        # O Odoo recalcula a empresa da ausência pelo calendário ao criar.
        self._feriado(False, dia=date(2026, 10, 20)).company_id = empresa
        slip = self._holerite(cal, l10n_br_horas_extras_50=10.0)
        he = self._get_line_total(slip, "HE_50")
        self.assertAlmostEqualMoney(
            self._get_line_total(slip, "DSR_HE"), round(he / 27 * 4, 2)
        )

    def test_feriado_global_sem_calendario_vale_para_todos(self):
        cal = self._calendario()
        self._feriado(False)
        slip = self._holerite(cal, l10n_br_horas_extras_50=10.0)
        he = self._get_line_total(slip, "HE_50")
        self.assertAlmostEqualMoney(
            self._get_line_total(slip, "DSR_HE"), round(he / 26 * 5, 2)
        )

    def test_ausencia_de_um_empregado_nao_e_feriado(self):
        cal = self._calendario()
        emp = self._create_employee("Com ausência")
        self._feriado(cal, resource_id=emp.resource_id.id)
        slip = self._holerite(cal, l10n_br_horas_extras_50=10.0)
        he = self._get_line_total(slip, "HE_50")
        self.assertAlmostEqualMoney(
            self._get_line_total(slip, "DSR_HE"), round(he / 27 * 4, 2)
        )


FUSOS_USUARIO = ("UTC", "America/Sao_Paulo", "Europe/Brussels")


class TestFeriadoPorFuso(BaseDsrReflexo):
    """O feriado vale igual para quem lança de qualquer fuso (TG-86 r2/r3)."""

    def _dsr_he(self, cal, **campos):
        slip = self._holerite(cal, l10n_br_horas_extras_50=10.0, **campos)
        he = self._get_line_total(slip, "HE_50")
        return self._get_line_total(slip, "DSR_HE"), he

    def _razao(self, cal):
        """Razão repouso/úteis efetiva: 5/26 com um feriado, 4/27 sem."""
        dsr, he = self._dsr_he(cal)
        for uteis, repouso in ((26, 5), (27, 4), (25, 6)):
            if abs(dsr - round(he / uteis * repouso, 2)) < 0.011:
                return uteis, repouso
        return None

    def _janela_segunda(self, cal):
        segunda = cal.attendance_ids.filtered(
            lambda m: not m.display_type and m.dayofweek == "0"
        )
        return min(segunda.mapped("hour_from")), max(segunda.mapped("hour_to"))

    def test_mesmo_resultado_em_qualquer_fuso_do_usuario(self):
        for fuso in FUSOS_USUARIO:
            with self.subTest(fuso=fuso):
                cal = self._calendario()
                self._feriado(cal, tz_usuario=fuso)
                self.assertEqual(self._razao(cal), (26, 5))

    def test_feriado_sem_calendario_lancado_em_sao_paulo(self):
        cal = self._calendario()
        self._feriado(False, tz_usuario="America/Sao_Paulo")
        self.assertEqual(self._razao(cal), (26, 5))

    def test_valores_crus_do_ci_em_fuso_a_leste(self):
        """O que o CI gravava: 03:00-23:59:59 UTC com calendário, usuário em Bruxelas.

        O Odoo regrava para 12/10 05:00 a 13/10 01:59:59 hora de São Paulo:
        cobre o expediente de 12/10 e só uma sobra de 13/10, que não é feriado.
        """
        cal = self._calendario()
        self._ausencia(
            cal,
            datetime(2026, 10, 12, 3),
            datetime(2026, 10, 12, 23, 59, 59),
            tz_usuario="Europe/Brussels",
        )
        self.assertEqual(self._razao(cal), (26, 5))

    def test_calendario_em_fuso_diferente_do_de_quem_lancou(self):
        """Calendário em UTC e feriado de São Paulo sem calendário.

        A ausência vai de 12/10 03:00Z a 13/10 02:59:59Z. No fuso do calendário
        (UTC) cobre o expediente de 12/10 e só uma sobra de madrugada de 13/10:
        é um feriado, não dois.
        """
        cal = self._calendario(tz="UTC")
        self._feriado(False, tz_usuario="America/Sao_Paulo")
        self.assertEqual(self._razao(cal), (26, 5))

    def test_casos_de_expediente_com_usuario_em_cada_fuso(self):
        """O mesmo caso, com o usuário em UTC, São Paulo e Bruxelas."""
        for fuso in FUSOS_USUARIO:
            cal = self._calendario()
            ini, fim = self._janela_segunda(cal)
            casos = {
                "expediente inteiro": (ini, fim, (26, 5)),
                "dia inteiro, fim à meia-noite": (0.0, 24.0, (26, 5)),
                "meio expediente": (ini, ini + 4.0, (27, 4)),
                "atraso de duas horas": (ini + 2.0, fim, (27, 4)),
            }
            for nome, (hora_ini, hora_fim, esperado) in casos.items():
                with self.subTest(fuso=fuso, caso=nome):
                    calendario = self._calendario()
                    self._ausencia_local(calendario, FERIADO, hora_ini, hora_fim, fuso)
                    self.assertEqual(self._razao(calendario), esperado)

    def test_recesso_de_varios_dias_nao_vira_repouso(self):
        """TG-86#P1: recesso coletivo de vários dias não conta como repouso."""
        for fuso in ("UTC", "America/Sao_Paulo"):
            with self.subTest(fuso=fuso):
                cal = self._calendario()
                # Uma ausência só, de 19 a 23/10 inteiros.
                self._ausencia_local(cal, date(2026, 10, 19), 0.0, 24.0 * 5, fuso)
                self.assertEqual(self._razao(cal), (27, 4))

    def test_dia_sem_expediente_usa_o_dia_local_inteiro(self):
        """Sábado de jornada seg-sex: só o dia local inteiro é feriado."""
        sabado = date(2026, 10, 31)
        for fuso in ("UTC", "America/Sao_Paulo"):
            with self.subTest(fuso=fuso, caso="dia inteiro"):
                cal = self._calendario()
                self._ausencia_local(cal, sabado, 0.0, 24.0, fuso)
                self.assertEqual(self._razao(cal), (26, 5))
            with self.subTest(fuso=fuso, caso="horário comercial"):
                cal = self._calendario()
                self._ausencia_local(cal, sabado, 8.0, 17.0, fuso)
                self.assertEqual(self._razao(cal), (27, 4))

    def test_calendario_sem_expediente_usa_o_dia_local_inteiro(self):
        cal = self._calendario()
        cal.attendance_ids.unlink()
        self._ausencia_local(cal, FERIADO, 0.0, 24.0, "America/Sao_Paulo")
        self.assertEqual(self._razao(cal), (26, 5))

    def _calendario_noturno(self):
        """Segunda 22h-24h e terça 0h-6h: um turno só, que cruza a meia-noite."""
        cal = self._calendario()
        cal.attendance_ids.unlink()
        turno = (("0", 22.0, 24.0), ("1", 0.0, 6.0))
        cal.write(
            {
                "attendance_ids": [
                    (
                        0,
                        0,
                        {"name": "Noite", "dayofweek": d, "hour_from": i, "hour_to": f},
                    )
                    for d, i, f in turno
                ]
            }
        )
        return cal

    def test_turno_noturno_parcial_nao_e_feriado(self):
        cal = self._calendario_noturno()
        self._ausencia_local(cal, FERIADO, 20.0, 24.0, "America/Sao_Paulo")
        self.assertEqual(self._razao(cal), (27, 4))

    def test_turno_noturno_completo_e_feriado_do_dia_de_inicio(self):
        """22h de segunda às 6h de terça: feriado de segunda (12/10), só ele."""
        cal = self._calendario_noturno()
        self._ausencia_local(cal, FERIADO, 22.0, 30.0, "America/Sao_Paulo")
        self.assertEqual(self._razao(cal), (26, 5))


class TestMigracaoDsr(PayrollCommon):
    """A migração liga as rubricas à estrutura CLT, uma vez e sem sobrepor."""

    def _migrar(self):
        caminho = file_path(
            "l10n_br_hr_payroll/migrations/18.0.1.5.0/post-migration.py"
        )
        spec = importlib.util.spec_from_file_location("post_migration_tg86", caminho)
        modulo = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(modulo)
        modulo.migrate(self.env.cr, "18.0.1.4.0")

    def test_liga_as_rubricas_de_forma_idempotente(self):
        regras = self.env.ref("l10n_br_hr_payroll.hr_rule_dsr_he") | self.env.ref(
            "l10n_br_hr_payroll.hr_rule_dsr_noturno"
        )
        self.structure_clt.write({"rule_ids": [(3, r.id) for r in regras]})
        self.assertFalse(set(regras.ids) & set(self.structure_clt.rule_ids.ids))
        self._migrar()
        self._migrar()
        self.assertTrue(set(regras.ids) <= set(self.structure_clt.rule_ids.ids))
        codigos = self.structure_clt.rule_ids.mapped("code")
        self.assertEqual(codigos.count("DSR_HE"), 1)
        self.assertEqual(codigos.count("DSR_NOTURNO"), 1)

    def test_troca_a_rubrica_do_ponto_pela_da_folha(self):
        """Banco atualizado converge para o de banco novo: só a rubrica da folha."""
        padrao = self.env.ref("l10n_br_hr_payroll.hr_rule_dsr_he")
        outra = self.env.ref(
            "l10n_br_hr_payroll_attendance.hr_rule_dsr_he", raise_if_not_found=False
        )
        if not outra:  # o ponto não está instalado: simula a rubrica dele
            outra = padrao.copy({"name": "DSR HE do ponto"})
            self.env["ir.model.data"].create(
                {
                    "module": "l10n_br_hr_payroll_attendance",
                    "name": "hr_rule_dsr_he",
                    "model": "hr.salary.rule",
                    "res_id": outra.id,
                }
            )
        self.structure_clt.write({"rule_ids": [(3, padrao.id), (4, outra.id)]})
        self._migrar()
        self._migrar()
        self.assertEqual(self.structure_clt.rule_ids.mapped("code").count("DSR_HE"), 1)
        self.assertIn(padrao, self.structure_clt.rule_ids)
        self.assertNotIn(outra, self.structure_clt.rule_ids)
