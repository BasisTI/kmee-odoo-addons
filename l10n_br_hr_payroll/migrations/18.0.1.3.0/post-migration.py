# Copyright 2024 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""TG-84: o desconto de DSR por falta passa a ser por semana com falta.

As regras são ``noupdate``, então a fórmula nova só chega ao banco existente
por aqui. Regra que alguém personalizou fica como está.
"""

import logging

from lxml import etree

from odoo import SUPERUSER_ID, api
from odoo.tools import file_open

_logger = logging.getLogger(__name__)

XMLID = "hr_rule_desc_dsr"
FORMULA_ANTIGA = """dias_uteis, dsr_mes = tools.br.dias_dsr()
result = tools.br.round_money((contract.wage / 30) * payslip.l10n_br_faltas_injustificadas * dsr_mes / dias_uteis)"""  # noqa: B950


def _campo_novo(campo):
    with file_open("l10n_br_hr_payroll/data/hr_salary_rule_data.xml", "rb") as arq:
        arvore = etree.parse(arq)
    return arvore.xpath(f"//record[@id='{XMLID}']/field[@name='{campo}']")[0].text


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    regra = env.ref(f"l10n_br_hr_payroll.{XMLID}", raise_if_not_found=False)
    if not regra:
        return
    if (regra.amount_python_compute or "").strip() == FORMULA_ANTIGA.strip():
        regra.write(
            {
                "condition_python": _campo_novo("condition_python"),
                "amount_python_compute": _campo_novo("amount_python_compute"),
            }
        )
        _logger.info("TG-84: fórmula de %s atualizada", XMLID)
    else:
        _logger.info("TG-84: %s personalizada, mantida", XMLID)
