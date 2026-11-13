# Copyright 2026 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
# flake8: noqa: B950
"""TG-130: saldo de salário sem resíduo de R$ 0,01 contra o mensal já pago.

A regra é ``noupdate="1"``: o ``-u`` não troca a fórmula de bancos
instalados. Recebe a fórmula nova SOMENTE se a gravada ainda for exatamente a
da 1.3.0 (TG-88); regra personalizada fica como está. Idempotente.
"""
import logging

from lxml import etree

from odoo import SUPERUSER_ID, api
from odoo.tools import file_open

_logger = logging.getLogger(__name__)

XMLID = "hr_rule_saldo_salario"
ARQUIVO = "hr_salary_rule_rescisao_data.xml"

FORMULA_ANTIGA = """# Dias de salário do contrato dentro do período do holerite (mês comercial de
# 30 dias): cobre a rescisão em qualquer dia do mês e o contrato iniciado no
# MEIO do mês, e já tira os dias de férias gozadas, pagos no recibo de férias
# (tools.br.dias_salario é o mesmo cálculo de dias do holerite mensal).
dias = tools.br.dias_salario(contract)
# Compensa o que o holerite mensal do mesmo período já pagou de salário
# (evita pagar os mesmos dias duas vezes); sem mensal, paga o saldo inteiro.
# Periculosidade/insalubridade dos mesmos dias (TG-88), também compensadas.
remuneracao = contract.wage + tools.br.adicionais_fixos(contract)
saldo = (remuneracao / 30) * dias - tools.br.salario_pago_mensal(contract, True)
result = tools.br.round_money(max(saldo, 0))"""


def _formula_nova():
    with file_open(f"l10n_br_hr_vacation/data/{ARQUIVO}", "rb") as arq:
        campo = etree.parse(arq).xpath(
            f"//record[@id='{XMLID}']/field[@name='amount_python_compute']"
        )
    return campo[0].text


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    regra = env.ref(f"l10n_br_hr_vacation.{XMLID}", raise_if_not_found=False)
    if not regra:
        return
    if (regra.amount_python_compute or "").strip() == FORMULA_ANTIGA.strip():
        regra.amount_python_compute = _formula_nova()
        _logger.info("TG-130: fórmula de %s atualizada", XMLID)
    else:
        _logger.info("TG-130: %s personalizada ou já atualizada, mantida", XMLID)
