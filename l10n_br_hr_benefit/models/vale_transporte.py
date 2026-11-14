# Copyright 2024 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""Cálculo puro do vale-transporte: valor diário da tarifa x dias úteis.

Lei 7.418/85, art. 4º, parágrafo único, e Decreto 10.854/21, art. 110: o
empregador custeia o que exceder 6% do salário básico do empregado; o crédito
cobre os dias em que há deslocamento para o trabalho.
"""
from datetime import timedelta

from odoo.addons.l10n_br_hr_payroll.models.salary_rules_br import round_money


def dias_uteis_vt(inicio, fim, dias_semana, feriados=(), ausencias=()):
    """Dias de trabalho de ``inicio`` a ``fim`` (inclusive) que geram VT.

    Args:
        inicio: Primeiro dia da janela (``date``): início do período do
            holerite ou a admissão, o que vier depois.
        fim: Último dia da janela: fim do período ou desligamento, o que vier
            antes.
        dias_semana: Dias da semana da escala do empregado (0 = segunda).
        feriados: Datas de feriado, que não geram VT.
        ausencias: Pares ``(inicio, fim)`` de afastamentos, licenças e férias
            gozadas, com todos os dias descontados.

    Returns:
        Número de dias úteis (int).
    """
    feriados = set(feriados or ())
    dias_semana = set(dias_semana)
    total = 0
    dia = inicio
    while dia <= fim:
        if (
            dia.weekday() in dias_semana
            and dia not in feriados
            and not any(ini <= dia <= term for ini, term in ausencias)
        ):
            total += 1
        dia += timedelta(days=1)
    return total


def credito_vt(valor_diario, dias_uteis):
    """Crédito do VT do mês: valor diário da tarifa x dias úteis."""
    return round_money(valor_diario * dias_uteis)
