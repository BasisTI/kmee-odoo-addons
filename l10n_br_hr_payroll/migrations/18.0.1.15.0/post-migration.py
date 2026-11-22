# Copyright 2026 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""TG-166: horista (unidade do salário Hora) e a regra DSR_HORISTA.

Os dados são ``noupdate="1"``: o ``-u`` cria a regra ``DSR_HORISTA``, mas não
troca as fórmulas nem a estrutura já gravadas. Aqui:

- ``HE_50``, ``HE_100`` e ``ADICIONAL_NOTURNO``: a linha do salário-hora passa a
  ``contract._l10n_br_salario_hora()`` (igual ao divisor da jornada para o
  mensalista), só se a linha for exatamente a da 1.14.0; o resto da fórmula
  fica como está;
- ``SALARIO_BASE``, ``FALTAS`` (condição) e ``DESC_DSR``: troca só se a fórmula
  gravada for exatamente a da 1.14.0; personalizada fica como está, com WARNING;
- ``DSR_HORISTA`` entra na estrutura CLT, se ainda não está.

Idempotente. Holerite calculado não muda; o em rascunho recalcula. Nada muda
para o mensalista.
"""
import logging

from lxml import etree

from odoo import SUPERUSER_ID, api
from odoo.tools import file_open

_logger = logging.getLogger(__name__)

LINHA_ANTIGA = "salario_hora = contract.wage / contract._l10n_br_divisor_horas_mensais()"
LINHA_NOVA = "salario_hora = contract._l10n_br_salario_hora()"
REGRAS_DE_HORA = ("hr_rule_he_50", "hr_rule_he_100", "hr_rule_adicional_noturno")

ANTIGAS = {
    ("hr_rule_salario_base", "amount_python_compute"): """
dias = tools.br.dias_salario(contract) - tools.br.dias_maternidade(contract)
result = tools.br.round_money(contract.wage * dias / 30)
""",
    ("hr_rule_faltas", "condition_python"): """
result = payslip.l10n_br_faltas_injustificadas > 0
""",
    ("hr_rule_desc_dsr", "amount_python_compute"): """
result = tools.br.round_money((contract.wage / 30) * tools.br.semanas_com_falta(contract))
""",
}


def _normaliza(texto):
    return "\n".join(
        linha.strip() for linha in (texto or "").strip().splitlines() if linha.strip()
    )


def _texto_novo(xmlid, campo):
    with file_open("l10n_br_hr_payroll/data/hr_salary_rule_data.xml", "rb") as arq:
        arvore = etree.parse(arq)
    achado = arvore.xpath(f"//record[@id='{xmlid}']/field[@name='{campo}']")
    return achado[0].text.strip("\n") if achado else None


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    for xmlid in REGRAS_DE_HORA:
        regra = env.ref(f"l10n_br_hr_payroll.{xmlid}", False)
        if not regra:
            continue
        linhas = (regra.amount_python_compute or "").splitlines()
        if any(linha.strip() == LINHA_ANTIGA for linha in linhas):
            regra.amount_python_compute = "\n".join(
                LINHA_NOVA if linha.strip() == LINHA_ANTIGA else linha
                for linha in linhas
            )
        elif LINHA_NOVA not in (regra.amount_python_compute or ""):
            _logger.warning(
                "TG-166: %s personalizada; use contract._l10n_br_salario_hora() "
                "no salário-hora para o horista",
                regra.code,
            )
    for (xmlid, campo), antigo in ANTIGAS.items():
        regra = env.ref(f"l10n_br_hr_payroll.{xmlid}", False)
        if not regra:
            continue
        atual = regra[campo]
        novo = _texto_novo(xmlid, campo)
        if novo is None or _normaliza(atual) == _normaliza(novo):
            continue
        if _normaliza(atual) == _normaliza(antigo):
            regra[campo] = novo
        else:
            _logger.warning(
                "TG-166: %s (%s) personalizada, não foi trocada; confira o ramo "
                "do horista (contract._l10n_br_horista())",
                regra.code,
                campo,
            )
    dsr = env.ref("l10n_br_hr_payroll.hr_rule_dsr_horista", False)
    clt = env.ref("l10n_br_hr_payroll.structure_clt", False)
    if dsr and clt and dsr not in clt.rule_ids:
        clt.rule_ids = [(4, dsr.id)]
