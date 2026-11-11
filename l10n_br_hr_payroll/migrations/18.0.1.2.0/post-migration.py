# Copyright 2024 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""INSS do mensal apurado na competência, com as férias gozadas (TG-83).

O XML das regras é ``noupdate="1"``: um ``-u`` não troca a fórmula de bancos já
instalados. A regra INSS padrão recebe a fórmula nova SOMENTE se a gravada ainda
for exatamente a antiga; regra personalizada fica como está.
"""
import logging

from lxml import etree

from odoo import SUPERUSER_ID, api
from odoo.tools import file_open

_logger = logging.getLogger(__name__)

XMLID = "hr_rule_inss"
FORMULA_ANTIGA = """base_inss = categories.GROSS - FALTAS - DESC_DSR
result = tools.br.calc_inss(max(base_inss, 0))"""


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
        _logger.info("TG-83: fórmula de %s atualizada", XMLID)
    else:
        _logger.info("TG-83: %s personalizada, mantida", XMLID)
