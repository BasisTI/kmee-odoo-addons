# Copyright 2024 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""Cálculo puro do vale-transporte: valor diário da tarifa x dias úteis.

Lei 7.418/85, art. 4º, parágrafo único, e Decreto 10.854/21, art. 110: o
empregador custeia o que exceder 6% do salário básico do empregado; o crédito
cobre os dias em que há deslocamento para o trabalho.
"""
from datetime import datetime, time, timedelta

from odoo.addons.l10n_br_hr_payroll.models.salary_rules_br import round_money


def dias_cobertos(inicio, fim, ausencias, tolerancia_min=1):
    """Dias inteiros (0h às 24h, hora local) cobertos por alguma ausência global.

    Serve ao recesso de vários dias, que o critério de feriado do DSR (um dia
    só) deixa de fora. ``ausencias`` são pares ``(inicio, fim)`` de
    ``datetime`` locais, sem fuso.
    """
    folga = timedelta(minutes=tolerancia_min)
    cobertos = set()
    for ini, term in ausencias:
        dia = ini.date()
        while dia <= term.date():
            meia_noite = datetime.combine(dia, time(0, 0))
            if (
                inicio <= dia <= fim
                and ini <= meia_noite + folga
                and term >= meia_noite + timedelta(days=1) - folga
            ):
                cobertos.add(dia)
            dia += timedelta(days=1)
    return cobertos


def dias_uteis_vt(inicio, fim, dias_semana, feriados=(), ausencias=()):
    """Dias de trabalho de ``inicio`` a ``fim`` (inclusive) que geram VT.

    Args:
        inicio: Primeiro dia da janela (``date``): início do período do
            holerite ou a admissão, o que vier depois.
        fim: Último dia da janela: fim do período ou desligamento, o que vier
            antes.
        dias_semana: Dias da semana da escala do empregado (0 = segunda), ou
            função ``f(date) -> bool`` que diz se o empregado trabalha no dia
            (escala quinzenal, como a 12x36).
        feriados: Datas de feriado, que não geram VT.
        ausencias: Pares ``(inicio, fim)`` de afastamentos, licenças e férias
            gozadas, com todos os dias descontados.

    Returns:
        Número de dias úteis (int).
    """
    feriados = set(feriados or ())
    trabalha = (
        dias_semana
        if callable(dias_semana)
        else (lambda dia, dias=set(dias_semana): dia.weekday() in dias)
    )
    total = 0
    dia = inicio
    while dia <= fim:
        if (
            trabalha(dia)
            and dia not in feriados
            and not any(ini <= dia <= term for ini, term in ausencias)
        ):
            total += 1
        dia += timedelta(days=1)
    return total


def credito_vt(valor_diario, dias_uteis):
    """Crédito do VT do mês: valor diário da tarifa x dias úteis."""
    return round_money(valor_diario * dias_uteis)
