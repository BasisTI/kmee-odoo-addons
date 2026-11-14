# Copyright 2026 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
# flake8: noqa: B950
"""TG-141: a rescisão desconta o 13º pago além do devido.

Regras e estruturas são ``noupdate="1"``: o ``-u`` cria as regras novas
(``DECIMO_DEVIDO``, ``DESCONTO_13_EXCESSO``, a linha informativa e as devoluções
de INSS e de IRRF do 13º), mas não as liga à estrutura da rescisão nem troca as fórmulas em
bancos instalados. Aqui as regras novas entram na estrutura e as fórmulas passam
a usar o 13º devido SOMENTE se a gravada ainda for exatamente a da 1.9.0; regra
personalizada fica como está, com aviso no log. Idempotente.
"""
import logging

from lxml import etree

from odoo import SUPERUSER_ID, api
from odoo.tools import file_open

_logger = logging.getLogger(__name__)

CAMPOS = {
    # (xmlid, campo): (arquivo, valor da 1.9.0)
    ("hr_rule_decimo_rescisao", "amount_python_compute"): (
        "hr_salary_rule_13_data.xml",
        r"""
# RF-18: base soma a média de horas extras/adicional noturno habituais.
avos = payslip.l10n_br_avos_13
media = tools.br.media_habitual(payslip._l10n_br_codes_media_habitual())
fator = payslip._l10n_br_fator_rescisao('decimo')
devido = tools.br.round_money((contract.wage + media + tools.br.adicionais_fixos(contract)) * avos / 12 * fator)
# TG-97: o 13º que a 2ª parcela (ou o 13º integral) confirmada já quitou no
# ano não se paga de novo: só a diferença dos avos. A 1ª parcela (adiantamento)
# não entra aqui: sai como desconto próprio (ADIANTAMENTO_13).
quitado = payslip._l10n_br_decimo_pago_ano(contract)['quitado']
result = max(devido - quitado, 0.0)
        """,
    ),
    ("hr_rule_inss_13_rescisao", "amount_python_compute"): (
        "hr_salary_rule_rescisao_data.xml",
        r"""
# TG-97: INSS sobre o 13º total do ano (o desta rescisão mais o que a 2ª
# parcela já quitou), menos o já retido nela.
pago = payslip._l10n_br_decimo_pago_ano(contract)
result = max(tools.br.calc_inss(max(DECIMO_RESCISAO, 0) + pago['quitado']) - pago['inss'], 0.0)
        """,
    ),
    ("hr_rule_pensao_13_rescisao", "amount_python_compute"): (
        "hr_salary_rule_rescisao_data.xml",
        r"""
# TG-97: percentual sobre o 13º total do ano, menos o já retido na 2ª parcela.
pago = payslip._l10n_br_decimo_pago_ano(contract)
result = max(
    tools.br.calc_pensao_alimenticia(
        max(DECIMO_RESCISAO, 0) + pago['quitado'],
        0.0,
        employee.l10n_br_pensao_percentual,
    ) - pago['pensao'],
    0.0,
)
        """,
    ),
    ("hr_rule_base_irrf_13_rescisao", "amount_python_compute"): (
        "hr_salary_rule_rescisao_data.xml",
        r"""
dependentes = employee.l10n_br_irrf_dependentes * tools.br.irrf_deducao_dependente()
# Pensão retida sobre o próprio 13º (percentual) - dedutível também na
# apuração exclusiva de fonte da gratificação natalina.
# TG-97: base anual do 13º, com o INSS e a pensão já retidos na 2ª parcela.
pago = payslip._l10n_br_decimo_pago_ano(contract)
result = (
    DECIMO_RESCISAO + pago['quitado']
    - INSS_13 - pago['inss']
    - dependentes
    - PENSAO_ALIMENTICIA_13 - pago['pensao']
)
        """,
    ),
    ("hr_rule_irrf_13_rescisao", "amount_python_compute"): (
        "hr_salary_rule_rescisao_data.xml",
        r"""
# RF-16: forma mais favorável DENTRO da apuração exclusiva do 13º da rescisão,
# seguida do redutor do IRPF sobre o 13º bruto (Lei 9.250/95, art. 3º-A, § 3º,
# dispositivo expresso para a gratificação natalina). Simplificado do 13º:
# IN RFB 1.500/2014, art. 13, § 8º.
# TG-97: imposto exclusivo do 13º total do ano, menos o retido na 2ª parcela.
pago = payslip._l10n_br_decimo_pago_ano(contract)
total = max(DECIMO_RESCISAO, 0) + pago['quitado']
result = max(tools.br.irrf_mais_favoravel(total, BASE_IRRF_13) - pago['irrf'], 0.0)
        """,
    ),
    ("hr_rule_fgts_13_rescisao", "amount_python_compute"): (
        "hr_salary_rule_rescisao_data.xml",
        r"""
# O FGTS das 1ªs parcelas do 13º do ano já foi recolhido na competência delas
# (TG-93): a rescisão recolhe só o que falta, sem valor negativo.
# Com a 2ª parcela já paga (TG-97), a base é o 13º total do ano e o recolhido
# soma as duas parcelas.
ja_recolhido = payslip._l10n_br_fgts_13_primeira_depositado(contract)
quitado = payslip._l10n_br_decimo_pago_ano(contract)['quitado']
result = max(
    tools.br.round_money((max(DECIMO_RESCISAO, 0) + quitado) * 0.08) - ja_recolhido, 0.0
)
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
    - ADIANTAMENTO_13
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
    "hr_rule_decimo_devido",
    "hr_rule_desconto_13_excesso",
    "hr_rule_nao_descontado_13_excesso",
    "hr_rule_devolucao_inss_13",
    "hr_rule_devolucao_irrf_13",
)


def _valor_novo(arquivo, xmlid, campo):
    with file_open(f"l10n_br_hr_vacation/data/{arquivo}", "rb") as arq:
        no = etree.parse(arq).xpath(f"//record[@id='{xmlid}']/field[@name='{campo}']")
    return no[0].text


def _normaliza(texto):
    return (texto or "").replace("\r\n", "\n").strip()


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    # As fórmulas novas leem o 13º devido e o NET novo soma a devolução e subtrai
    # o desconto: com o NET personalizado, trocar só as outras (ou ligar as regras
    # novas) deixaria o líquido diferente da soma das linhas. Nada é alterado.
    net = env.ref("l10n_br_hr_vacation.hr_rule_net_rescisao", raise_if_not_found=False)
    chave = ("hr_rule_net_rescisao", "amount_python_compute")
    if net and _normaliza(net[chave[1]]) not in (
        _normaliza(CAMPOS[chave][1]),
        _normaliza(_valor_novo(CAMPOS[chave][0], *chave)),
    ):
        _logger.warning(
            "TG-141: o NET da rescisão está personalizado: NENHUMA regra foi "
            "atualizada nem ligada à estrutura, para o líquido não divergir das "
            "linhas. Compare com l10n_br_hr_vacation/data/ (13º devido, desconto "
            "do excesso e devoluções de INSS e IRRF do 13º) e ajuste."
        )
        return
    for (xmlid, campo), (arquivo, antigo) in CAMPOS.items():
        regra = env.ref(f"l10n_br_hr_vacation.{xmlid}", raise_if_not_found=False)
        if not regra:
            continue
        if _normaliza(regra[campo]) == _normaliza(antigo):
            regra.write({campo: _valor_novo(arquivo, xmlid, campo)})
            _logger.info("TG-141: %s.%s atualizado", xmlid, campo)
        elif _normaliza(regra[campo]) == _normaliza(_valor_novo(arquivo, xmlid, campo)):
            _logger.info("TG-141: %s.%s já atualizado", xmlid, campo)
        else:
            _logger.warning(
                "TG-141: a regra '%s' (%s) está personalizada e NÃO foi atualizada "
                "(campo %s). Sem ela, a rescisão não desconta o 13º pago além do "
                "devido nem devolve os encargos retidos a mais: compare com "
                "l10n_br_hr_vacation/data/ e ajuste.",
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
            _logger.info("TG-141: %s ligada à estrutura da rescisão", xmlid)
