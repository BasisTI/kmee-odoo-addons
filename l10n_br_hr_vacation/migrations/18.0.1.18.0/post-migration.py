# Copyright 2026 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""TG-163: FGTS do 13º do aprendiz em banco vindo da 1.8.0 ou da 1.9.0.

A migração 18.0.1.10.0 (TG-141) grava nas regras de FGTS do 13º a fórmula do XML
vigente (já com os 2% do aprendiz), mas não toca na condição. A 18.0.1.14.0
(TG-138) então vê a fórmula "já atualizada" e passa direto, sem trocar a condição:
a regra fica com ``condition_select = 'python'`` e
``result = employee.l10n_br_tipo_contrato != 'aprendiz'``, e a rescisão do
aprendiz sai sem FGTS do 13º.

Aqui, nas três regras de FGTS do 13º, o estado exato "fórmula atual + condição
padrão antiga" passa a ``condition_select = 'none'``. Condição diferente da
conhecida é personalização: fica como está, registrada no log em nível INFO (não
é defeito do banco; o cliente decidiu). Regra com fórmula diferente da atual não
é tocada (a 18.0.1.14.0 cuida dela). Holerites já calculados não mudam (o aberto
recalcula no próximo cálculo; o confirmado não é tocado). Idempotente.
"""
import logging

from lxml import etree

from odoo import SUPERUSER_ID, api
from odoo.tools import file_open

_logger = logging.getLogger(__name__)

CONDICAO_ANTIGA = "result = employee.l10n_br_tipo_contrato != 'aprendiz'"

# (xmlid, arquivo)
REGRAS = (
    ("hr_rule_fgts_13_primeira", "hr_salary_rule_13_data.xml"),
    ("hr_rule_fgts_13", "hr_salary_rule_13_data.xml"),
    ("hr_rule_fgts_13_rescisao", "hr_salary_rule_rescisao_data.xml"),
)


def _valor_novo(arquivo, xmlid):
    with file_open(f"l10n_br_hr_vacation/data/{arquivo}", "rb") as arq:
        no = etree.parse(arq).xpath(
            f"//record[@id='{xmlid}']/field[@name='amount_python_compute']"
        )
    return no[0].text


def _normaliza(texto):
    return (texto or "").replace("\r\n", "\n").strip()


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    for xmlid, arquivo in REGRAS:
        regra = env.ref(f"l10n_br_hr_vacation.{xmlid}", raise_if_not_found=False)
        if not regra:
            continue
        if regra.condition_select != "python":
            _logger.info("TG-163: %s sem condição, nada a fazer", xmlid)
            continue
        if _normaliza(regra.amount_python_compute) != _normaliza(
            _valor_novo(arquivo, xmlid)
        ):
            _logger.info(
                "TG-163: %s com fórmula diferente da atual, condição mantida", xmlid
            )
            continue
        if _normaliza(regra.condition_python) != CONDICAO_ANTIGA:
            _logger.info(
                "TG-163: a condição de '%s' (%s) está personalizada e foi mantida "
                "(o aprendiz continua sem FGTS no 13º se ela o exclui).",
                regra.name,
                xmlid,
            )
            continue
        regra.write({"condition_select": "none"})
        _logger.info("TG-163: %s sem a condição que excluía o aprendiz", xmlid)
