# Copyright 2026 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""TG-128: adicional noturno pela hora reduzida e percentual do contrato.

A 18.0.1.4.0 só trocava a fórmula com ``round_money`` e divisor da jornada.
Banco instalado antes de 03/2026 tem a fórmula com divisor fixo 220, com ou sem
``round_money``, e continuava pagando o adicional sobre horas de relógio. A
regra é ``noupdate``: a fórmula nova só chega por aqui. Fórmula que alguém
personalizou fica como está. O divisor que a regra já usava é mantido (220
continua 220: as outras regras de hora desse banco também seguem nele).
Idempotente (a fórmula nova não é nenhuma das antigas).

Também alinha a marca de hora reduzida dos holerites em rascunho ao contrato;
o confirmado ou pago guarda o que valeu.
"""

import logging

from lxml import etree

from odoo import SUPERUSER_ID, api
from odoo.tools import file_open

_logger = logging.getLogger(__name__)

XMLID = "hr_rule_adicional_noturno"
DIVISOR_JORNADA = "contract._l10n_br_divisor_horas_mensais()"

_SALARIO_HORA = (
    "salario_hora = contract.wage / 220",
    f"salario_hora = contract.wage / {DIVISOR_JORNADA}",
)
_RESULTADO = (
    "result = salario_hora * 0.20 * payslip.l10n_br_horas_noturnas",
    "result = tools.br.round_money(salario_hora * 0.20 * payslip.l10n_br_horas_noturnas)",  # noqa: B950
    # padrão da 18.0.1.4.0 em diante, anterior ao percentual do contrato
    "result = tools.br.round_money(salario_hora * 0.20 * payslip.l10n_br_horas_noturnas_computadas)",  # noqa: B950
)


def _normaliza(texto):
    return "\n".join(
        linha.strip() for linha in (texto or "").strip().splitlines() if linha.strip()
    )


# Divisor (220 fixo ou da jornada) x resultado (com/sem arredondamento, sobre
# o relógio ou o computado) que o padrão do módulo já teve.
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
    atual = _normaliza(regra.amount_python_compute)
    if atual not in FORMULAS_ANTIGAS:
        _logger.info("TG-128: %s já atual ou personalizada, mantida", XMLID)
        return False
    nova = _formula_nova()
    if "contract.wage / 220" in atual:
        nova = nova.replace(DIVISOR_JORNADA, "220")
    regra.amount_python_compute = nova
    _logger.info("TG-128: fórmula de %s atualizada", XMLID)
    return True


def alinhar_rascunhos(cr):
    cr.execute(
        """UPDATE hr_payslip p
              SET l10n_br_usar_hora_reduzida = c.l10n_br_hora_noturna_reduzida
             FROM hr_contract c
            WHERE c.id = p.contract_id
              AND p.state IN ('draft', 'verify')
              AND p.l10n_br_usar_hora_reduzida IS DISTINCT FROM
                  c.l10n_br_hora_noturna_reduzida"""
    )
    _logger.info(
        "TG-128: %s holerite(s) em rascunho alinhados ao contrato", cr.rowcount
    )


def migrate(cr, version):
    atualizar_formula(api.Environment(cr, SUPERUSER_ID, {}))
    alinhar_rascunhos(cr)
