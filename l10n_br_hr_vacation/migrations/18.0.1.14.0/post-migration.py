# Copyright 2026 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""TG-138: base da multa do FGTS, FGTS do 13º do aprendiz e 13º genérico.

Regras e estruturas são ``noupdate="1"``: o ``-u`` não troca as fórmulas de
bancos instalados. Aqui:

- ``MULTA_FGTS`` passa a somar só o FGTS do 13º ainda fora do saldo
  (``_l10n_br_fgts_13_na_base_multa``);
- as três regras de FGTS do 13º (1ª parcela, 2ª parcela/13º e rescisão) passam
  a recolher 2% do aprendiz (hoje não recolhem nada) e deixam de ter condição;
- a estrutura ``13_SALARIO`` ganha o desconto do adiantamento.

Cada regra só é trocada se a gravada for exatamente a da versão anterior; a
personalizada fica como está, com aviso no log (e o aviso na tela do holerite
da rescisão, ``l10n_br_aviso_regras``). Holerites já calculados não mudam.
Idempotente.
"""
import logging

from lxml import etree

from odoo import SUPERUSER_ID, api
from odoo.tools import file_open

_logger = logging.getLogger(__name__)

ALIQUOTA = "(0.02 if employee.l10n_br_tipo_contrato == 'aprendiz' else 0.08)"
CONDICAO_ANTIGA = "result = employee.l10n_br_tipo_contrato != 'aprendiz'"

# (xmlid, arquivo, troca nova -> antiga na fórmula, troca a condição?)
REGRAS = (
    (
        "hr_rule_multa_fgts",
        "hr_salary_rule_rescisao_data.xml",
        (("_l10n_br_fgts_13_na_base_multa", "_l10n_br_fgts_13_primeira_depositado"),),
        False,
    ),
    (
        "hr_rule_fgts_13_primeira",
        "hr_salary_rule_13_data.xml",
        ((ALIQUOTA, "0.08"),),
        True,
    ),
    ("hr_rule_fgts_13", "hr_salary_rule_13_data.xml", ((ALIQUOTA, "0.08"),), True),
    (
        "hr_rule_fgts_13_rescisao",
        "hr_salary_rule_rescisao_data.xml",
        ((ALIQUOTA, "0.08"),),
        True,
    ),
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
    for xmlid, arquivo, trocas, condicao in REGRAS:
        regra = env.ref(f"l10n_br_hr_vacation.{xmlid}", raise_if_not_found=False)
        if not regra:
            continue
        novo = _valor_novo(arquivo, xmlid)
        antigo = novo
        for nova, velha in trocas:
            antigo = antigo.replace(nova, velha)
        atual = _normaliza(regra.amount_python_compute)
        if atual == _normaliza(novo):
            _logger.info("TG-138: %s já atualizada", xmlid)
            continue
        if atual != _normaliza(antigo):
            _logger.warning(
                "TG-138: a regra '%s' (%s) está personalizada e NÃO foi atualizada. "
                "Compare com l10n_br_hr_vacation/data/ (base da multa do FGTS e "
                "FGTS de 2%% do aprendiz no 13º) e ajuste.",
                regra.name,
                xmlid,
            )
            continue
        valores = {"amount_python_compute": novo}
        if condicao:
            if _normaliza(regra.condition_python) == CONDICAO_ANTIGA:
                valores.update(condition_select="none")
            else:
                _logger.warning(
                    "TG-138: a condição de '%s' (%s) está personalizada e foi mantida "
                    "(o aprendiz continua sem FGTS no 13º se ela o exclui).",
                    regra.name,
                    xmlid,
                )
        regra.write(valores)
        _logger.info("TG-138: %s atualizada", xmlid)
    estrutura = env.ref("l10n_br_hr_vacation.structure_13", raise_if_not_found=False)
    desconto = env.ref(
        "l10n_br_hr_vacation.hr_rule_desconto_adiantamento_13",
        raise_if_not_found=False,
    )
    if estrutura and desconto and desconto not in estrutura.rule_ids:
        estrutura.write({"rule_ids": [(4, desconto.id)]})
        _logger.info("TG-138: adiantamento do 13º ligado à estrutura 13_SALARIO")
