# Copyright 2026 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
# flake8: noqa: B950
"""TG-88: periculosidade e insalubridade na base de férias, 13º e rescisão.

As regras são ``noupdate="1"``: o ``-u`` não troca a fórmula de bancos
instalados. Cada regra padrão recebe a fórmula nova SOMENTE se a gravada ainda
for exatamente a antiga; regra personalizada fica como está. Idempotente (a
fórmula já atualizada não é igual à antiga, então nada acontece na repetição).
"""
import logging

from lxml import etree

from odoo import SUPERUSER_ID, api
from odoo.tools import file_open

_logger = logging.getLogger(__name__)

ARQUIVOS = {
    "hr_rule_ferias": "hr_salary_rule_ferias_data.xml",
    "hr_rule_abono_pecuniario": "hr_salary_rule_ferias_data.xml",
    "hr_rule_adiantamento_13": "hr_salary_rule_13_data.xml",
    "hr_rule_decimo_bruto": "hr_salary_rule_13_data.xml",
    "hr_rule_decimo_rescisao": "hr_salary_rule_13_data.xml",
    "hr_rule_saldo_salario": "hr_salary_rule_rescisao_data.xml",
    "hr_rule_ferias_indenizadas": "hr_salary_rule_rescisao_data.xml",
    "hr_rule_ferias_vencidas": "hr_salary_rule_rescisao_data.xml",
    "hr_rule_aviso_previo_indenizado": "hr_salary_rule_rescisao_data.xml",
}

FORMULAS_ANTIGAS = {
    "hr_rule_ferias": """# Férias proporcionais aos dias gozados: ao vender o abono (10 dias), o
# empregado goza 20 dias => 20/30 do salário (CLT art. 143). RF-18: a base
# soma a média das verbas variáveis habituais dos últimos 12 meses (Súmula
# 45 TST / CLT art. 142), não só o salário contratual seco.
media = tools.br.media_habitual(payslip._l10n_br_codes_media_habitual())
dias_gozados = payslip.l10n_br_dias_ferias_gozadas
result = tools.br.round_money((contract.wage + media) * dias_gozados / 30)""",
    "hr_rule_abono_pecuniario": """# RF-19: dias vendidos vêm de l10n_br_dias_ferias_vendidas, que já resolve
# o caminho novo (l10n_br_dias_abono, com alocação/fracionamento) e o
# legado (30 - dias gozados, sem alocação, venda fixa de 1/3 de 30 dias).
dias_vendidos = payslip.l10n_br_dias_ferias_vendidas
result = tools.br.round_money((contract.wage / 30) * dias_vendidos)""",
    "hr_rule_adiantamento_13": """# 1ª parcela = 50% do 13º projetado para 31/12 (proporcional aos avos).
# Para empregado de ano cheio, avos=12 => 50% do salário.
# Para admitido no meio do ano, proporcional aos meses trabalhados.
# RF-18: base soma a média de horas extras/adicional noturno habituais.
ref = payslip.date_to.replace(month=12, day=31)
avos = tools.br.calc_decimo_avos(contract.date_start, ref)
media = tools.br.media_habitual(payslip._l10n_br_codes_media_habitual())
result = tools.br.round_money((contract.wage + media) * avos / 12 * 0.5)""",
    "hr_rule_decimo_bruto": """# RF-18: base soma a média de horas extras/adicional noturno habituais.
avos = payslip.l10n_br_avos_13
media = tools.br.media_habitual(payslip._l10n_br_codes_media_habitual())
result = tools.br.round_money((contract.wage + media) * avos / 12)""",
    "hr_rule_decimo_rescisao": """# RF-18: base soma a média de horas extras/adicional noturno habituais.
avos = payslip.l10n_br_avos_13
media = tools.br.media_habitual(payslip._l10n_br_codes_media_habitual())
result = tools.br.round_money((contract.wage + media) * avos / 12)""",
    "hr_rule_saldo_salario": """# Dias de salário do contrato dentro do período do holerite (mês comercial de
# 30 dias): cobre a rescisão em qualquer dia do mês e o contrato iniciado no
# MEIO do mês, e já tira os dias de férias gozadas, pagos no recibo de férias
# (tools.br.dias_salario é o mesmo cálculo de dias do holerite mensal).
dias = tools.br.dias_salario(contract)
# Compensa o que o holerite mensal do mesmo período já pagou de salário
# (evita pagar os mesmos dias duas vezes); sem mensal, paga o saldo inteiro.
saldo = (contract.wage / 30) * dias - tools.br.salario_pago_mensal(contract)
result = tools.br.round_money(max(saldo, 0))""",
    "hr_rule_ferias_indenizadas": """# RF-18: base soma a média de horas extras/adicional noturno habituais.
avos = payslip.l10n_br_avos_ferias
media = tools.br.media_habitual(payslip._l10n_br_codes_media_habitual())
result = tools.br.round_money((contract.wage + media) * avos / 12)""",
    "hr_rule_ferias_vencidas": """# RF-18: também soma a média habitual, como qualquer verba de férias.
media = tools.br.media_habitual(payslip._l10n_br_codes_media_habitual())
salario_dia = (contract.wage + media) / 30
result = tools.br.round_money(sum(
    salario_dia * periodo["dias"] * (2 if periodo["dobro"] else 1)
    for periodo in payslip._l10n_br_ferias_vencidas_dados()
))""",
    "hr_rule_aviso_previo_indenizado": """# Acordo (CLT art. 484-A, I, "a"): aviso pago pela METADE. Sem justa causa:
# integral. Súmula 94 TST: a base soma a média das verbas habituais.
dias = payslip._l10n_br_dias_aviso_previo()
media = tools.br.media_habitual(payslip._l10n_br_codes_media_habitual())
fator = 0.5 if payslip.l10n_br_tipo_rescisao == 'acordo' else 1.0
result = tools.br.round_money((contract.wage + media) / 30 * dias * fator)""",
}


def _formula_nova(xmlid):
    with file_open(f"l10n_br_hr_vacation/data/{ARQUIVOS[xmlid]}", "rb") as arq:
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
        if (regra.amount_python_compute or "").strip() == antiga.strip():
            regra.amount_python_compute = _formula_nova(xmlid)
            _logger.info("TG-88: fórmula de %s atualizada", xmlid)
        else:
            _logger.info("TG-88: %s personalizada ou já atualizada, mantida", xmlid)
