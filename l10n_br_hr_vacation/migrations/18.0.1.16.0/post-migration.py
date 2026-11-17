# Copyright 2026 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
# flake8: noqa: B950
"""TG-149: FGTS de 2% e INSS do aprendiz nas férias e no saldo de salário da rescisão.

Regras são ``noupdate="1"``: o ``-u`` não troca as regras de bancos instalados.
Aqui, as quatro regras que excluíam o aprendiz pela condição
(``employee.l10n_br_tipo_contrato != 'aprendiz'``) passam a valer para ele:

- ``hr_rule_fgts_ferias`` e ``hr_rule_fgts_rescisao`` (FGTS de férias e do saldo
  de salário): a condição some e a fórmula passa a usar 2% no aprendiz (Lei
  8.036/90, art. 15 §7º) e 8% nos demais;
- ``hr_rule_inss_rescisao`` e ``hr_rule_inss_13_rescisao``: só a condição some
  (a fórmula já é a da tabela do INSS).

As fórmulas "antigas" abaixo são as da 1.14.0, copiadas dela (não derivadas do
XML final). A regra só é trocada se a condição e a fórmula gravadas forem
exatamente as da 1.14.0; a personalizada fica como está, com aviso no log. Em
particular, uma fórmula de FGTS personalizada com a condição padrão NÃO tem a
condição removida: o aprendiz passaria a receber 8%. Idempotente; holerites já
calculados não mudam.
"""
import logging

from lxml import etree

from odoo import SUPERUSER_ID, api
from odoo.tools import file_open

_logger = logging.getLogger(__name__)

CONDICAO_ANTIGA = "result = employee.l10n_br_tipo_contrato != 'aprendiz'"

# (xmlid, arquivo, fórmula gravada na 1.14.0, ou None se a fórmula não muda)
REGRAS = (
    (
        "hr_rule_fgts_ferias",
        "hr_salary_rule_ferias_data.xml",
        "result = tools.br.round_money(max(categories.GROSS, 0) * 0.08)",
    ),
    (
        "hr_rule_fgts_rescisao",
        "hr_salary_rule_rescisao_data.xml",
        "result = tools.br.round_money(max(SALDO_SALARIO, 0) * 0.08)",
    ),
    ("hr_rule_inss_rescisao", "hr_salary_rule_rescisao_data.xml", None),
    ("hr_rule_inss_13_rescisao", "hr_salary_rule_rescisao_data.xml", None),
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
    for xmlid, arquivo, formula_antiga in REGRAS:
        regra = env.ref(f"l10n_br_hr_vacation.{xmlid}", raise_if_not_found=False)
        if not regra:
            continue
        sem_condicao = regra.condition_select == "none"
        condicao_antiga = (
            regra.condition_select == "python"
            and _normaliza(regra.condition_python) == CONDICAO_ANTIGA
        )
        novo = _valor_novo(arquivo, xmlid)
        formula_atual = _normaliza(regra.amount_python_compute)
        formula_ok = (
            formula_antiga is None or formula_atual == _normaliza(novo)
            if sem_condicao
            else formula_antiga is None or formula_atual == _normaliza(formula_antiga)
        )
        if sem_condicao and formula_ok:
            _logger.info("TG-149: %s já atualizada", xmlid)
            continue
        if not (condicao_antiga and formula_ok):
            _logger.warning(
                "TG-149: a regra '%s' (%s) está personalizada e NÃO foi atualizada. "
                "Compare com l10n_br_hr_vacation/data/ (FGTS de 2%% e INSS do "
                "aprendiz nas férias e no saldo de salário da rescisão) e ajuste: "
                "sem isso o aprendiz continua sem a regra, ou com o percentual "
                "errado.",
                regra.name,
                xmlid,
            )
            continue
        valores = {"condition_select": "none"}
        if formula_antiga is not None:
            valores["amount_python_compute"] = novo
        regra.write(valores)
        _logger.info("TG-149: %s atualizada", xmlid)
