# Copyright 2026 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""TG-128: a migração do adicional noturno cobre as fórmulas padrão antigas.

A 18.0.1.4.0 só trocava a fórmula com ``round_money`` e divisor da jornada.
Banco instalado antes de 03/2026 tem a fórmula com divisor fixo 220, com ou sem
``round_money``, e continuava pagando o adicional sobre horas de relógio. A
regra é ``noupdate``: a fórmula nova só chega por aqui. Fórmula que alguém
personalizou fica como está. Idempotente (a fórmula nova não é nenhuma das antigas).
"""

import logging

from lxml import etree

from odoo import SUPERUSER_ID, api
from odoo.tools import file_open

_logger = logging.getLogger(__name__)

XMLID = "hr_rule_adicional_noturno"

_SALARIO_HORA = (
    "salario_hora = contract.wage / 220",
    "salario_hora = contract.wage / contract._l10n_br_divisor_horas_mensais()",
)
_RESULTADO = (
    "result = salario_hora * 0.20 * payslip.l10n_br_horas_noturnas",
    "result = tools.br.round_money(salario_hora * 0.20 * payslip.l10n_br_horas_noturnas)",  # noqa: B950
)


def _normaliza(texto):
    return "\n".join(
        linha.strip() for linha in (texto or "").strip().splitlines() if linha.strip()
    )


# As quatro combinações de divisor (220 fixo ou da jornada) e arredondamento
# que o padrão do módulo já teve.
FORMULAS_ANTIGAS = {
    _normaliza(f"{salario}\n{resultado}")
    for salario in _SALARIO_HORA
    for resultado in _RESULTADO
}


def _formula_nova():
    with file_open("l10n_br_hr_payroll/data/hr_salary_rule_data.xml", "rb") as arq:
        arvore = etree.parse(arq)
    campo = arvore.xpath(
        f"//record[@id='{XMLID}']/field[@name='amount_python_compute']"
    )
    return campo[0].text


def atualizar_formula(env):
    regra = env.ref(f"l10n_br_hr_payroll.{XMLID}", raise_if_not_found=False)
    if not regra:
        return False
    if _normaliza(regra.amount_python_compute) in FORMULAS_ANTIGAS:
        regra.amount_python_compute = _formula_nova()
        _logger.info("TG-128: fórmula de %s atualizada", XMLID)
        return True
    _logger.info("TG-128: %s já atual ou personalizada, mantida", XMLID)
    return False


def migrate(cr, version):
    atualizar_formula(api.Environment(cr, SUPERUSER_ID, {}))
