# Copyright 2026 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
# flake8: noqa: B950
"""TG-94: o abono pecuniário leva as médias de variáveis.

A regra é ``noupdate="1"``: o ``-u`` não troca a fórmula em bancos instalados.
Aqui ela é trocada SOMENTE se a gravada ainda for exatamente a da 1.6.0; regra
personalizada fica como está. Idempotente.
"""
import logging

from lxml import etree

from odoo import SUPERUSER_ID, api
from odoo.tools import file_open

_logger = logging.getLogger(__name__)

ANTIGA = """dias_vendidos = payslip.l10n_br_dias_ferias_vendidas
result = tools.br.round_money(((contract.wage + tools.br.adicionais_fixos(contract)) / 30) * dias_vendidos)"""


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    regra = env.ref(
        "l10n_br_hr_vacation.hr_rule_abono_pecuniario", raise_if_not_found=False
    )
    if not regra:
        return
    gravada = (regra.amount_python_compute or "").replace("\r\n", "\n").strip()
    if not gravada.endswith(ANTIGA):
        _logger.info("TG-94: abono personalizado ou já atualizado, mantido")
        return
    with file_open(
        "l10n_br_hr_vacation/data/hr_salary_rule_ferias_data.xml", "rb"
    ) as arq:
        campo = etree.parse(arq).xpath(
            "//record[@id='hr_rule_abono_pecuniario']"
            "/field[@name='amount_python_compute']"
        )
    regra.write({"amount_python_compute": campo[0].text})
    _logger.info("TG-94: fórmula do abono atualizada")
