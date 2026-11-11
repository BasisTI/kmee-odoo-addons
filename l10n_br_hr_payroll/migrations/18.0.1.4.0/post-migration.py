# Copyright 2024 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""TG-85: o adicional noturno incide sobre as horas pela hora reduzida.

As regras são ``noupdate``, então a fórmula nova só chega ao banco existente
por aqui. Regra que alguém personalizou fica como está.
"""

import logging

from lxml import etree

from odoo import SUPERUSER_ID, api
from odoo.tools import file_open

_logger = logging.getLogger(__name__)

XMLID = "hr_rule_adicional_noturno"
FORMULA_ANTIGA = """salario_hora = contract.wage / contract._l10n_br_divisor_horas_mensais()
result = tools.br.round_money(salario_hora * 0.20 * payslip.l10n_br_horas_noturnas)"""  # noqa: B950


def _formula_nova():
    with file_open("l10n_br_hr_payroll/data/hr_salary_rule_data.xml", "rb") as arq:
        arvore = etree.parse(arq)
    campo = arvore.xpath(
        f"//record[@id='{XMLID}']/field[@name='amount_python_compute']"
    )
    return campo[0].text


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    regra = env.ref(f"l10n_br_hr_payroll.{XMLID}", raise_if_not_found=False)
    if not regra:
        return
    if (regra.amount_python_compute or "").strip() == FORMULA_ANTIGA.strip():
        regra.amount_python_compute = _formula_nova()
        _logger.info("TG-85: fórmula de %s atualizada", XMLID)
    else:
        _logger.info("TG-85: %s personalizada, mantida", XMLID)
