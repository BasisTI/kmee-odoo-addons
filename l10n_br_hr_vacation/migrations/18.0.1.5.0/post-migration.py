# Copyright 2026 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
# flake8: noqa: B950
"""TG-92: multa do FGTS informativa (fora do NET) e sobre a base completa.

As regras são ``noupdate="1"``: o ``-u`` não troca a fórmula de bancos
instalados. Cada regra recebe a fórmula nova SOMENTE se a gravada ainda for
exatamente a da 1.4.0; regra personalizada fica como está. A multa também
passa para a sequência 152 (depois dos FGTS da rescisão, que a base soma),
junto com a sua fórmula. Idempotente.
"""
import logging

from lxml import etree

from odoo import SUPERUSER_ID, api
from odoo.tools import file_open

_logger = logging.getLogger(__name__)

ARQUIVO = "hr_salary_rule_rescisao_data.xml"

FORMULAS_ANTIGAS = {
    "hr_rule_multa_fgts": """if payslip.l10n_br_fgts_saldo_conta:
    base = payslip.l10n_br_fgts_saldo_conta
else:
    # Fallback documentado: 8% do salário por mês trabalhado, sem
    # juros/correção monetária - subestima o saldo real da conta
    # vinculada. Preencher l10n_br_fgts_saldo_conta com o extrato do FGTS
    # Digital sempre que disponível.
    meses = tools.br.meses_trabalhados(contract.date_start, payslip.date_to)
    aliq_fgts = 0.02 if employee.l10n_br_tipo_contrato == 'aprendiz' else 0.08
    base = tools.br.round_money(contract.wage * aliq_fgts * meses)
percentual = 0.20 if payslip.l10n_br_tipo_rescisao == 'acordo' else 0.40
result = tools.br.round_money(base * percentual)""",
    "hr_rule_net_rescisao": """result = (
    SALDO_SALARIO
    + DECIMO_RESCISAO
    + FERIAS_INDENIZADAS
    + ADICIONAL_FERIAS_INDENIZADAS
    + FERIAS_VENCIDAS
    + ADICIONAL_FERIAS_VENCIDAS
    + AVISO_PREVIO_INDENIZADO
    + MULTA_FGTS
    - INSS
    - INSS_13
    - IRRF
    - IRRF_13
    - PENSAO_ALIMENTICIA
    - PENSAO_ALIMENTICIA_13
)""",
}


def _formula_nova(xmlid):
    with file_open(f"l10n_br_hr_vacation/data/{ARQUIVO}", "rb") as arq:
        campo = etree.parse(arq).xpath(
            f"//record[@id='{xmlid}']/field[@name='amount_python_compute']"
        )
    return campo[0].text


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    for xmlid, antiga in FORMULAS_ANTIGAS.items():
        regra = env.ref(f"l10n_br_hr_vacation.{xmlid}", raise_if_not_found=False)
        if not regra:
            continue
        # Fórmula regravada com CRLF (editada no Windows) ainda é a original.
        gravada = (regra.amount_python_compute or "").replace("\r\n", "\n")
        if gravada.strip() == antiga.strip():
            valores = {"amount_python_compute": _formula_nova(xmlid)}
            if xmlid == "hr_rule_multa_fgts":
                valores["sequence"] = 152
            regra.write(valores)
            _logger.info("TG-92: fórmula de %s atualizada", xmlid)
        else:
            _logger.info("TG-92: %s personalizada ou já atualizada, mantida", xmlid)
