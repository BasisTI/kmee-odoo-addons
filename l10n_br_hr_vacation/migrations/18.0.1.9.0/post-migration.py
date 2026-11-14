# Copyright 2026 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
# flake8: noqa: B950
"""TG-97: a rescisão desconta o 13º do ano já pago (1ª e 2ª parcelas).

Regras e estruturas são ``noupdate="1"``: o ``-u`` cria as regras novas
(``ADIANTAMENTO_13`` da rescisão e a linha informativa), mas não as liga à
estrutura da rescisão nem troca as fórmulas em bancos instalados. Aqui as
regras novas entram na estrutura e as fórmulas passam a descontar o 13º pago
SOMENTE se a gravada ainda for exatamente a da 1.8.0; regra personalizada
fica como está, com aviso no log. Idempotente.
"""
import logging

from lxml import etree

from odoo import SUPERUSER_ID, api
from odoo.tools import file_open

_logger = logging.getLogger(__name__)

CAMPOS = {
    # (xmlid, campo): (arquivo, valor da 1.8.0)
    ("hr_rule_decimo_rescisao", "amount_python_compute"): (
        "hr_salary_rule_13_data.xml",
        r"""
# RF-18: base soma a média de horas extras/adicional noturno habituais.
avos = payslip.l10n_br_avos_13
media = tools.br.media_habitual(payslip._l10n_br_codes_media_habitual())
fator = payslip._l10n_br_fator_rescisao('decimo')
result = tools.br.round_money((contract.wage + media + tools.br.adicionais_fixos(contract)) * avos / 12 * fator)
        """,
    ),
    ("hr_rule_inss_13_rescisao", "amount_python_compute"): (
        "hr_salary_rule_rescisao_data.xml",
        r"""
result = tools.br.calc_inss(max(DECIMO_RESCISAO, 0))
        """,
    ),
    ("hr_rule_pensao_13_rescisao", "amount_python_compute"): (
        "hr_salary_rule_rescisao_data.xml",
        r"""
result = tools.br.calc_pensao_alimenticia(
    max(DECIMO_RESCISAO, 0),
    0.0,
    employee.l10n_br_pensao_percentual,
)
        """,
    ),
    ("hr_rule_base_irrf_13_rescisao", "amount_python_compute"): (
        "hr_salary_rule_rescisao_data.xml",
        r"""
dependentes = employee.l10n_br_irrf_dependentes * tools.br.irrf_deducao_dependente()
# Pensão retida sobre o próprio 13º (percentual) - dedutível também na
# apuração exclusiva de fonte da gratificação natalina.
result = DECIMO_RESCISAO - INSS_13 - dependentes - PENSAO_ALIMENTICIA_13
        """,
    ),
    ("hr_rule_irrf_13_rescisao", "amount_python_compute"): (
        "hr_salary_rule_rescisao_data.xml",
        r"""
# RF-16: forma mais favorável DENTRO da apuração exclusiva do 13º da rescisão,
# seguida do redutor do IRPF sobre o 13º bruto (Lei 9.250/95, art. 3º-A, § 3º,
# dispositivo expresso para a gratificação natalina). Simplificado do 13º:
# IN RFB 1.500/2014, art. 13, § 8º.
result = tools.br.irrf_mais_favoravel(max(DECIMO_RESCISAO, 0), BASE_IRRF_13)
        """,
    ),
    ("hr_rule_fgts_13_rescisao", "amount_python_compute"): (
        "hr_salary_rule_rescisao_data.xml",
        r"""
# O FGTS das 1ªs parcelas do 13º do ano já foi recolhido na competência delas
# (TG-93): a rescisão recolhe só o que falta, sem valor negativo.
ja_recolhido = payslip._l10n_br_fgts_13_primeira_depositado(contract)
result = max(
    tools.br.round_money(max(DECIMO_RESCISAO, 0) * 0.08) - ja_recolhido, 0.0
)
        """,
    ),
    ("hr_rule_desconto_aviso_previo", "amount_python_compute"): (
        "hr_salary_rule_rescisao_data.xml",
        r"""
# Súmula 94 TST: a base soma a média das verbas habituais.
media = tools.br.media_habitual(payslip._l10n_br_codes_media_habitual())
remuneracao = contract.wage + media + tools.br.adicionais_fixos(contract)
devido = tools.br.round_money(remuneracao)
# Não pode deixar o líquido negativo nem passar de um mês de remuneração (art.
# 477, §5º): desconta só o que sobra dos créditos depois dos descontos
# obrigatórios. O restante vai à linha informativa NAO_DESCONTADO_AVISO_PREVIO.
disponivel = (
    SALDO_SALARIO + DECIMO_RESCISAO + FERIAS_INDENIZADAS
    + ADICIONAL_FERIAS_INDENIZADAS + FERIAS_VENCIDAS + ADICIONAL_FERIAS_VENCIDAS
    + AVISO_PREVIO_INDENIZADO + INDENIZACAO_ART_479
    - INSS - INSS_13 - IRRF - IRRF_13 - PENSAO_ALIMENTICIA - PENSAO_ALIMENTICIA_13
)
result = tools.br.round_money(max(min(devido, disponivel, remuneracao), 0))
        """,
    ),
    ("hr_rule_desconto_art_480", "amount_python_compute"): (
        "hr_salary_rule_rescisao_data.xml",
        r"""
media = tools.br.media_habitual(payslip._l10n_br_codes_media_habitual())
remuneracao = contract.wage + media + tools.br.adicionais_fixos(contract)
devido = tools.br.round_money(payslip._l10n_br_desconto_art_480(remuneracao))
# Não pode deixar o líquido negativo: só o que sobra dos créditos depois dos
# descontos obrigatórios e do aviso não cumprido. Teto de um mês de remuneração
# para o conjunto das compensações (art. 477, §5º). O que não couber vai à
# linha informativa NAO_DESCONTADO_ART_480.
disponivel = (
    SALDO_SALARIO + DECIMO_RESCISAO + FERIAS_INDENIZADAS
    + ADICIONAL_FERIAS_INDENIZADAS + FERIAS_VENCIDAS + ADICIONAL_FERIAS_VENCIDAS
    + AVISO_PREVIO_INDENIZADO + INDENIZACAO_ART_479
    - INSS - INSS_13 - IRRF - IRRF_13 - PENSAO_ALIMENTICIA - PENSAO_ALIMENTICIA_13
)
result = tools.br.round_money(max(min(devido, disponivel - DESCONTO_AVISO_PREVIO, remuneracao - DESCONTO_AVISO_PREVIO), 0))
        """,
    ),
    ("hr_rule_net_rescisao", "amount_python_compute"): (
        "hr_salary_rule_rescisao_data.xml",
        r"""
result = (
    SALDO_SALARIO
    + DECIMO_RESCISAO
    + FERIAS_INDENIZADAS
    + ADICIONAL_FERIAS_INDENIZADAS
    + FERIAS_VENCIDAS
    + ADICIONAL_FERIAS_VENCIDAS
    + AVISO_PREVIO_INDENIZADO
    + INDENIZACAO_ART_479
    - DESCONTO_ART_480
    - DESCONTO_AVISO_PREVIO
    - INSS
    - INSS_13
    - IRRF
    - IRRF_13
    - PENSAO_ALIMENTICIA
    - PENSAO_ALIMENTICIA_13
)
        """,
    ),
}

NOVAS_NA_RESCISAO = (
    "hr_rule_desconto_adiantamento_13_rescisao",
    "hr_rule_nao_descontado_adiantamento_13",
)


def _valor_novo(arquivo, xmlid, campo):
    with file_open(f"l10n_br_hr_vacation/data/{arquivo}", "rb") as arq:
        no = etree.parse(arq).xpath(f"//record[@id='{xmlid}']/field[@name='{campo}']")
    return no[0].text


def _normaliza(texto):
    return (texto or "").replace("\r\n", "\n").strip()


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    for (xmlid, campo), (arquivo, antigo) in CAMPOS.items():
        regra = env.ref(f"l10n_br_hr_vacation.{xmlid}", raise_if_not_found=False)
        if not regra:
            continue
        if _normaliza(regra[campo]) == _normaliza(antigo):
            regra.write({campo: _valor_novo(arquivo, xmlid, campo)})
            _logger.info("TG-97: %s.%s atualizado", xmlid, campo)
        elif _normaliza(regra[campo]) == _normaliza(_valor_novo(arquivo, xmlid, campo)):
            _logger.info("TG-97: %s.%s já atualizado", xmlid, campo)
        else:
            _logger.warning(
                "TG-97: a regra '%s' (%s) está personalizada e NÃO foi atualizada "
                "(campo %s). Sem ela, a rescisão não desconta o 13º já pago "
                "(1ª e 2ª parcelas) nem abate o INSS, o IRRF e o FGTS já "
                "recolhidos: compare com l10n_br_hr_vacation/data/ e ajuste.",
                regra.name,
                xmlid,
                campo,
            )
    estrutura = env.ref(
        "l10n_br_hr_vacation.structure_rescisao", raise_if_not_found=False
    )
    if not estrutura:
        return
    for xmlid in NOVAS_NA_RESCISAO:
        regra = env.ref(f"l10n_br_hr_vacation.{xmlid}", raise_if_not_found=False)
        if regra and regra not in estrutura.rule_ids:
            estrutura.write({"rule_ids": [(4, regra.id)]})
            _logger.info("TG-97: %s ligada à estrutura da rescisão", xmlid)
