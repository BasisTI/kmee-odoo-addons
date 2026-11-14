# Copyright 2026 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
# flake8: noqa: B950
"""TG-110: o VT sai do valor diário da tarifa x dias úteis do mês.

Regras e estruturas são ``noupdate="1"``: o ``-u`` cria a regra ``VT_INFO``,
mas não troca a fórmula do ``DESC_VT`` nem liga a regra nova às estruturas em
bancos instalados. Aqui a fórmula troca SOMENTE se a gravada ainda for
exatamente a da 1.0.0; regra personalizada fica como está, com aviso no log.
Idempotente.
"""
import logging

from lxml import etree

from odoo import SUPERUSER_ID, api
from odoo.tools import file_open

_logger = logging.getLogger(__name__)

CAMPOS = {
    # (xmlid, campo): valor da 1.0.0
    (
        "hr_rule_desc_vt",
        "condition_python",
    ): r"""
vt = current_contract.advantages.VT
result = vt and vt > 0
        """,
    (
        "hr_rule_desc_vt",
        "amount_python_compute",
    ): r"""
vt = current_contract.advantages.VT
result = tools.br.calc_vt(contract.wage, vt)
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
            _logger.info("TG-110: %s.%s atualizado", xmlid, campo)
        elif _normaliza(regra[campo]) != _normaliza(novo):
            _logger.warning(
                "TG-110: a regra '%s' (%s) está personalizada e NÃO foi "
                "atualizada (campo %s). Sem a troca, o VT segue pelo valor "
                "mensal: compare com l10n_br_hr_benefit/data/ e ajuste.",
                regra.name,
                xmlid,
                campo,
            )
    vt_info = env.ref("l10n_br_hr_benefit.hr_rule_vt_info", raise_if_not_found=False)
    for xmlid in ESTRUTURAS:
        estrutura = env.ref(xmlid, raise_if_not_found=False)
        if vt_info and estrutura and vt_info not in estrutura.rule_ids:
            estrutura.write({"rule_ids": [(4, vt_info.id)]})
            _logger.info("TG-110: VT_INFO ligada a %s", xmlid)
