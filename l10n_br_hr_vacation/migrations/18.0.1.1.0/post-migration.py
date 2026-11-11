# Copyright 2024 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""Saldo de salário compensa o que o holerite mensal já pagou (TG-82).

O XML das regras é ``noupdate="1"``: troca a fórmula do ``SALDO_SALARIO`` só se
a gravada ainda for exatamente a antiga; regra personalizada fica como está.
"""
import logging

from lxml import etree

from odoo import SUPERUSER_ID, api
from odoo.tools import file_open

_logger = logging.getLogger(__name__)

FORMULA_ANTIGA = """# Dias de vigência do contrato dentro do período do holerite (mês
# comercial de 30 dias) - cobre tanto a rescisão em qualquer dia do mês
# quanto o contrato iniciado no MEIO do mês (tools.br.dias_trabalhados_mes
# já balanceia contra contract.date_start e contract.date_end).
dias = tools.br.dias_trabalhados_mes(contract)
result = tools.br.round_money((contract.wage / 30) * dias)"""


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    regra = env.ref("l10n_br_hr_vacation.hr_rule_saldo_salario", False)
    if not regra:
        return
    if (regra.amount_python_compute or "").strip() != FORMULA_ANTIGA.strip():
        _logger.info("TG-82: SALDO_SALARIO personalizada, mantida")
        return
    with file_open(
        "l10n_br_hr_vacation/data/hr_salary_rule_rescisao_data.xml", "rb"
    ) as arq:
        campo = etree.parse(arq).xpath(
            "//record[@id='hr_rule_saldo_salario']"
            "/field[@name='amount_python_compute']"
        )
    regra.amount_python_compute = campo[0].text
    _logger.info("TG-82: fórmula de SALDO_SALARIO atualizada")
