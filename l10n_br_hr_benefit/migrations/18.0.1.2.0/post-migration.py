# Copyright 2026 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
# flake8: noqa: B950
"""TG-111: desconto de VA/VR (071) por faixa da CCT e VT com o percentual da CCT.

Regras e estruturas são ``noupdate="1"``: o ``-u`` cria a regra ``DESC_VAVR``,
mas não troca a fórmula do ``DESC_VT`` (6% fixo, da 1.1.0) nem liga a regra nova
às estruturas em bancos instalados. A fórmula troca SOMENTE se a gravada ainda
for exatamente a da 1.1.0; regra personalizada fica como está, com aviso no log.
Idempotente.
"""
import logging

from lxml import etree

from odoo import SUPERUSER_ID, api
from odoo.tools import file_open

_logger = logging.getLogger(__name__)

CAMPOS = {
    # (xmlid, campo): valor da 1.1.0
    (
        "hr_rule_desc_vt",
        "amount_python_compute",
    ): r"""
# 6% só do salário-base do mês (sem variáveis), limitado ao custo do VT.
salario_base = tools.br.round_money(
    contract.wage * tools.br.dias_salario(contract) / 30
)
result = tools.br.calc_vt(salario_base, tools.br.credito_vt(contract))
        """,
}
ESTRUTURAS = (
    "l10n_br_hr_payroll.structure_clt",
    "l10n_br_hr_payroll.structure_estatuto",
)


def _valor_novo(xmlid, campo):
    with file_open(
        "l10n_br_hr_benefit/data/hr_salary_rule_benefit_data.xml", "rb"
    ) as arq:
        no = etree.parse(arq).xpath(f"//record[@id='{xmlid}']/field[@name='{campo}']")
    return no[0].text


def _normaliza(texto):
    return (texto or "").replace("\r\n", "\n").strip()


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    for (xmlid, campo), antigo in CAMPOS.items():
        regra = env.ref(f"l10n_br_hr_benefit.{xmlid}", raise_if_not_found=False)
        if not regra:
            continue
        novo = _valor_novo(xmlid, campo)
        if _normaliza(regra[campo]) == _normaliza(antigo):
            regra.write({campo: novo})
            _logger.info("TG-111: %s.%s atualizado", xmlid, campo)
        elif _normaliza(regra[campo]) != _normaliza(novo):
            _logger.warning(
                "TG-111: a regra '%s' (%s) está personalizada e NÃO foi "
                "atualizada (campo %s). Sem a troca, o VT segue com 6%% fixo: "
                "compare com l10n_br_hr_benefit/data/ e ajuste.",
                regra.name,
                xmlid,
                campo,
            )
    vavr = env.ref("l10n_br_hr_benefit.hr_rule_desc_vavr", raise_if_not_found=False)
    for xmlid in ESTRUTURAS:
        estrutura = env.ref(xmlid, raise_if_not_found=False)
        if vavr and estrutura and vavr not in estrutura.rule_ids:
            estrutura.write({"rule_ids": [(4, vavr.id)]})
            _logger.info("TG-111: DESC_VAVR ligada a %s", xmlid)
