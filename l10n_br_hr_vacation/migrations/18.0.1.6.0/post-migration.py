# Copyright 2026 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
# flake8: noqa: B950
"""TG-93: FGTS da 1ª parcela do 13º na competência do pagamento.

Estruturas e regras são ``noupdate="1"``: o ``-u`` cria a regra nova, mas não
a liga à estrutura da 1ª parcela nem troca as fórmulas em bancos instalados.
Aqui a regra nova entra na estrutura e as fórmulas do FGTS (13º) da 2ª
parcela, do FGTS (13º Rescisão) (abate o já recolhido nas 1ªs parcelas) e da
multa (base soma o FGTS das 1ªs parcelas) são trocadas SOMENTE se a gravada
ainda for exatamente a da 1.5.0; regra personalizada fica como está.
Idempotente.
"""
import logging

from lxml import etree

from odoo import SUPERUSER_ID, api
from odoo.tools import file_open

_logger = logging.getLogger(__name__)

FORMULAS = {
    # xmlid: (arquivo, fórmula da 1.5.0)
    "hr_rule_fgts_13": (
        "hr_salary_rule_13_data.xml",
        "result = tools.br.round_money(max(categories.GROSS, 0) * 0.08)",
    ),
    "hr_rule_fgts_13_rescisao": (
        "hr_salary_rule_rescisao_data.xml",
        "result = tools.br.round_money(max(DECIMO_RESCISAO, 0) * 0.08)",
    ),
    "hr_rule_multa_fgts": (
        "hr_salary_rule_rescisao_data.xml",
        """if payslip.l10n_br_fgts_saldo_conta:
    saldo = payslip.l10n_br_fgts_saldo_conta
else:
    # Fallback documentado: 8% do salário por mês completo trabalhado, sem
    # juros/correção monetária - subestima o saldo real da conta
    # vinculada. Preencher l10n_br_fgts_saldo_conta com o extrato do FGTS
    # Digital sempre que disponível.
    meses = tools.br.meses_trabalhados(contract.date_start, payslip.date_to)
    aliq_fgts = 0.02 if employee.l10n_br_tipo_contrato == 'aprendiz' else 0.08
    saldo = tools.br.round_money(contract.wage * aliq_fgts * meses)
depositos = (
    payslip._l10n_br_fgts_depositado_mensal(contract)
    + FGTS
    + FGTS_13
    + FGTS_AVISO
)
percentual = 0.20 if payslip.l10n_br_tipo_rescisao == 'acordo' else 0.40
result = tools.br.round_money((saldo + depositos) * percentual)
        """,
    ),
}


def _formula_nova(arquivo, xmlid):
    with file_open(f"l10n_br_hr_vacation/data/{arquivo}", "rb") as arq:
        campo = etree.parse(arq).xpath(
            f"//record[@id='{xmlid}']/field[@name='amount_python_compute']"
        )
    return campo[0].text


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    for xmlid, (arquivo, antiga) in FORMULAS.items():
        regra = env.ref(f"l10n_br_hr_vacation.{xmlid}", raise_if_not_found=False)
        if not regra:
            continue
        gravada = (regra.amount_python_compute or "").replace("\r\n", "\n")
        if gravada.strip() == antiga.strip():
            regra.write({"amount_python_compute": _formula_nova(arquivo, xmlid)})
            _logger.info("TG-93: fórmula de %s atualizada", xmlid)
        else:
            _logger.info("TG-93: %s personalizada ou já atualizada, mantida", xmlid)
    estrutura = env.ref(
        "l10n_br_hr_vacation.structure_13_primeira_parcela", raise_if_not_found=False
    )
    nova = env.ref(
        "l10n_br_hr_vacation.hr_rule_fgts_13_primeira", raise_if_not_found=False
    )
    if estrutura and nova and nova not in estrutura.rule_ids:
        estrutura.write({"rule_ids": [(4, nova.id)]})
        _logger.info("TG-93: FGTS da 1ª parcela ligado à estrutura")
