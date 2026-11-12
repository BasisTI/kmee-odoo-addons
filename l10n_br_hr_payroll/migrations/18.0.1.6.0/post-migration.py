# Copyright 2024 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""TG-87: salário-maternidade com rubrica própria.

As regras são ``noupdate``: as fórmulas novas do salário base, da CPP e do RAT
só chegam ao banco existente por aqui (regra personalizada fica como está), e
as rubricas novas entram na estrutura CLT. Os tipos de afastamento marcados
como licença-maternidade no ``l10n_br_esocial`` passam a usar o campo deste
módulo. Idempotente.
"""

import logging

from lxml import etree

from odoo import SUPERUSER_ID, api
from odoo.tools import file_open

_logger = logging.getLogger(__name__)

FORMULAS_ANTIGAS = {
    "hr_rule_salario_base": """# Proporcional aos dias de salário do mês (admissão, desligamento, afastamento
# previdenciário), em mês comercial de 30 dias.
result = tools.br.round_money(contract.wage * tools.br.dias_salario(contract) / 30)""",  # noqa: B950
    "hr_rule_cpp_patronal": """# Lei 8.212/91, art. 22, I: 20% sobre o total das remunerações, sem teto.
# Optante pela CPRB: alíquota reduzida pela proporção do ano na transição da
# Lei 14.973/2024 (a redução alcança SÓ este inciso - ver RAT e terceiros).
base_patronal = max(categories.GROSS - FALTAS - DESC_DSR, 0)
result = tools.br.round_money(base_patronal * tools.br.aliquotas_patronais(contract).cpp)""",  # noqa: B950
    "hr_rule_rat_patronal": """# Lei 8.212/91, art. 22, II (riscos ambientais do trabalho): 1%, 2% ou 3%
# pelo CNAE preponderante, multiplicado pelo FAP (Decreto 3.048/99,
# art. 202-A). INTEGRAL mesmo para optante da CPRB e INTEGRAL sobre o 13º.
# Só alcança segurado empregado: remuneração de contribuinte individual
# (pró-labore) é art. 22, III, sem RAT.
base_patronal = max(categories.GROSS - FALTAS - DESC_DSR, 0)
result = tools.br.round_money(base_patronal * tools.br.aliquotas_patronais(contract).rat)""",  # noqa: B950
}


def _formula_nova(xmlid):
    with file_open("l10n_br_hr_payroll/data/hr_salary_rule_data.xml", "rb") as arq:
        arvore = etree.parse(arq)
    campo = arvore.xpath(
        f"//record[@id='{xmlid}']/field[@name='amount_python_compute']"
    )
    return campo[0].text


def _copiar_marca_do_esocial(cr):
    """Quem já marcava "Licença-maternidade (eSocial)" mantém a marca."""
    cr.execute(
        """SELECT 1 FROM information_schema.columns
            WHERE table_name = 'hr_leave_type'
              AND column_name = 'l10n_br_esocial_salario_maternidade'"""
    )
    if not cr.fetchone():
        return
    cr.execute(
        """UPDATE hr_leave_type
              SET l10n_br_salario_maternidade = TRUE
            WHERE l10n_br_esocial_salario_maternidade IS TRUE"""
    )
    _logger.info("TG-87: %s tipo(s) de afastamento com a marca copiada", cr.rowcount)


def migrate(cr, version):
    _copiar_marca_do_esocial(cr)
    env = api.Environment(cr, SUPERUSER_ID, {})
    for xmlid, antiga in FORMULAS_ANTIGAS.items():
        regra = env.ref(f"l10n_br_hr_payroll.{xmlid}", raise_if_not_found=False)
        if not regra:
            continue
        if (regra.amount_python_compute or "").strip() == antiga.strip():
            regra.amount_python_compute = _formula_nova(xmlid)
            _logger.info("TG-87: fórmula de %s atualizada", xmlid)
        else:
            _logger.info("TG-87: %s personalizada ou já atualizada, mantida", xmlid)
    # Rubricas novas na estrutura CLT (estrutura noupdate; (4, id) é idempotente).
    estrutura = env.ref("l10n_br_hr_payroll.structure_clt", raise_if_not_found=False)
    if not estrutura:
        return
    for xmlid in ("hr_rule_salario_maternidade", "hr_rule_comp_salario_maternidade"):
        regra = env.ref(f"l10n_br_hr_payroll.{xmlid}", raise_if_not_found=False)
        if regra and regra not in estrutura.rule_ids:
            estrutura.write({"rule_ids": [(4, regra.id)]})
            _logger.info("TG-87: %s ligada à estrutura CLT", regra.code)
