# Copyright 2026 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
# flake8: noqa: B950
"""TG-93: FGTS da 1ª parcela do 13º na competência do pagamento.

Estruturas e regras são ``noupdate="1"``: o ``-u`` cria a regra nova, mas não
a liga à estrutura da 1ª parcela nem troca a fórmula do FGTS da 2ª parcela em
bancos instalados. Aqui a regra nova entra na estrutura e a fórmula do FGTS
(13º) passa a incidir só sobre a diferença para a 1ª parcela, SOMENTE se a
gravada ainda for exatamente a da 1.5.0; regra personalizada fica como está.
Idempotente.
"""
import logging

from lxml import etree

from odoo import SUPERUSER_ID, api
from odoo.tools import file_open

_logger = logging.getLogger(__name__)

ARQUIVO = "hr_salary_rule_13_data.xml"
XMLID = "hr_rule_fgts_13"
FORMULA_ANTIGA = "result = tools.br.round_money(max(categories.GROSS, 0) * 0.08)"


def _formula_nova():
    with file_open(f"l10n_br_hr_vacation/data/{ARQUIVO}", "rb") as arq:
        campo = etree.parse(arq).xpath(
            f"//record[@id='{XMLID}']/field[@name='amount_python_compute']"
        )
    return campo[0].text


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    regra = env.ref(f"l10n_br_hr_vacation.{XMLID}", raise_if_not_found=False)
    if regra:
        gravada = (regra.amount_python_compute or "").replace("\r\n", "\n")
        if gravada.strip() == FORMULA_ANTIGA:
            regra.write({"amount_python_compute": _formula_nova()})
            _logger.info("TG-93: fórmula de %s atualizada", XMLID)
        else:
            _logger.info("TG-93: %s personalizada ou já atualizada, mantida", XMLID)
    estrutura = env.ref(
        "l10n_br_hr_vacation.structure_13_primeira_parcela", raise_if_not_found=False
    )
    nova = env.ref(
        "l10n_br_hr_vacation.hr_rule_fgts_13_primeira", raise_if_not_found=False
    )
    if estrutura and nova and nova not in estrutura.rule_ids:
        estrutura.write({"rule_ids": [(4, nova.id)]})
        _logger.info("TG-93: FGTS da 1ª parcela ligado à estrutura")
