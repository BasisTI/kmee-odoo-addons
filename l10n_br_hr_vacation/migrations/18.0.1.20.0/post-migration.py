# Copyright 2026 KMEE
# flake8: noqa: B950
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""TG-168: férias, 13º e rescisão do horista nas fórmulas já gravadas.

As regras são ``noupdate="1"``: o ``-u`` não troca a fórmula gravada. A 18.0.1.20.0
passa a base ``contract.wage`` a ``tools.br.salario_referencia(contract, ...)`` (o
mesmo valor para o mensalista; a média das horas para o horista) e o saldo de
salário da rescisão ganha o ramo do horista.

A fórmula só é trocada se a gravada for exatamente a anterior (comparação que
ignora espaços nas pontas das linhas e linhas em branco). Personalizada fica como
está, com WARNING: o horista dela continua com ``contract.wage`` (o mensal de
referência) até o cliente ajustar. Idempotente.
"""
import logging
import re

from lxml import etree

from odoo import SUPERUSER_ID, api
from odoo.tools import file_open

_logger = logging.getLogger(__name__)

ARQUIVOS = (
    "hr_salary_rule_ferias_data.xml",
    "hr_salary_rule_13_data.xml",
    "hr_salary_rule_rescisao_data.xml",
)
SALARIO_REFERENCIA = re.compile(
    r"tools\.br\.salario_referencia\(contract, '\w+'(?:, \([^)]*\))?\)"
)
SALDO_NOVO = """if contract._l10n_br_horista():
    # Horista (TG-168): as horas do holerite x valor-hora e o repouso; compensa
    # o salário e o repouso que o mensal do período já pagou.
    salario = tools.br.round_money(contract._l10n_br_salario_hora() * tools.br.horas_horista()) + tools.br.dsr_horista()
else:
    salario = (
        tools.br.round_money(contract.wage * (dias - maternidade) / 30)
        + tools.br.round_money(contract.wage * maternidade / 30)
    )
saldo = salario + tools.br.adicionais_fixos_dias(contract, dias) - tools.br.salario_pago_mensal(contract, True, True)"""
SALDO_ANTIGO = """salario = (
    tools.br.round_money(contract.wage * (dias - maternidade) / 30)
    + tools.br.round_money(contract.wage * maternidade / 30)
)
saldo = salario + tools.br.adicionais_fixos_dias(contract, dias) - tools.br.salario_pago_mensal(contract, True)"""


def _normaliza(texto):
    return "\n".join(
        linha.strip() for linha in (texto or "").strip().splitlines() if linha.strip()
    )


def _antiga(nova):
    """A fórmula da 18.0.1.19.0: a nova com as trocas desfeitas."""
    return SALARIO_REFERENCIA.sub(
        "contract.wage", nova.replace(SALDO_NOVO, SALDO_ANTIGO)
    )


def _regras_novas():
    """``{xmlid: fórmula nova}`` das regras que o TG-168 mexeu."""
    achadas = {}
    for arquivo in ARQUIVOS:
        with file_open(f"l10n_br_hr_vacation/data/{arquivo}", "rb") as arq:
            arvore = etree.parse(arq)
        for campo in arvore.xpath("//record/field[@name='amount_python_compute']"):
            texto = campo.text or ""
            if "salario_referencia" in texto or SALDO_NOVO in texto:
                achadas[campo.getparent().get("id")] = texto
    return achadas


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    for xmlid, nova in _regras_novas().items():
        regra = env.ref(f"l10n_br_hr_vacation.{xmlid}", raise_if_not_found=False)
        if not regra:
            continue
        atual = _normaliza(regra.amount_python_compute)
        if atual == _normaliza(nova):
            continue
        if atual == _normaliza(_antiga(nova)):
            regra.amount_python_compute = nova.strip("\n")
            _logger.info("TG-168: %s com a base do horista", xmlid)
        else:
            _logger.warning(
                "TG-168: %s personalizada, não foi trocada; para o horista use "
                "tools.br.salario_referencia(contract, verba) no lugar de "
                "contract.wage",
                regra.name,
            )
