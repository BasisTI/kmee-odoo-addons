# Copyright 2024 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""Fórmulas proporcionais aos dias de salário (TG-82).

O XML das regras é ``noupdate="1"``: um ``-u`` não troca a fórmula de bancos já
instalados. Aqui cada regra padrão recebe a fórmula nova SOMENTE se a gravada
ainda for exatamente a antiga; regra personalizada fica como está.
"""
import logging

from lxml import etree

from odoo import SUPERUSER_ID, api
from odoo.tools import file_open

_logger = logging.getLogger(__name__)

FORMULAS_ANTIGAS = {
    "hr_rule_salario_base": "result = contract.wage",
    "hr_rule_periculosidade": "result = tools.br.round_money(contract.wage * 0.30)",
    "hr_rule_insalubridade": """SM = tools.br.salario_minimo()
grau = contract.l10n_br_grau_insalubridade
percentuais = {'minimo': 0.10, 'medio': 0.20, 'maximo': 0.40}
result = tools.br.round_money(SM * percentuais.get(grau, 0.10))""",
}


def _formulas_novas():
    with file_open("l10n_br_hr_payroll/data/hr_salary_rule_data.xml", "rb") as arq:
        arvore = etree.parse(arq)
    novas = {}
    for xmlid in FORMULAS_ANTIGAS:
        campo = arvore.xpath(
            f"//record[@id='{xmlid}']/field[@name='amount_python_compute']"
        )
        novas[xmlid] = campo[0].text
    return novas


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    novas = _formulas_novas()
    for xmlid, antiga in FORMULAS_ANTIGAS.items():
        regra = env.ref(f"l10n_br_hr_payroll.{xmlid}", raise_if_not_found=False)
        if not regra:
            continue
        if (regra.amount_python_compute or "").strip() == antiga.strip():
            regra.amount_python_compute = novas[xmlid]
            _logger.info("TG-82: fórmula de %s atualizada", xmlid)
        else:
            _logger.info("TG-82: %s personalizada, mantida", xmlid)
