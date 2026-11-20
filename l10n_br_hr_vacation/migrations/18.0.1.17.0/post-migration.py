# Copyright 2026 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
# flake8: noqa: B950
"""TG-151: as regras de desconto da rescisão, de qualquer versão antiga à atual.

As migrações 18.0.1.11.0 (TG-136) e 18.0.1.12.0 (TG-133) derivavam a fórmula
"antiga" do XML final, que já traz a mudança da outra. Num upgrade vindo da
1.10.0 que atravessa as duas, nenhuma reconhecia a fórmula gravada, e
``DESCONTO_ART_480``, ``DESCONTO_AVISO_PREVIO`` e ``DESCONTO_13_EXCESSO`` ficavam
com a fórmula da 1.10.0: sem ``DECIMO_AVISO_INDENIZADO`` no "disponível" e com
``tools.br.adicionais_fixos(contract)`` sem a verba.

Aqui as fórmulas de cada versão anterior estão copiadas dela (não derivadas do
XML final): a da 1.10.0 e a da 1.11.0 (1.10.0 com a rubrica nova no
"disponível"; a 1.12.0 é a atual). A regra gravada com qualquer uma delas
passa à fórmula atual; a regra já atual fica como está; a personalizada de
verdade fica preservada, com aviso no log. Holerites já calculados não mudam
(o aberto recalcula no próximo cálculo; o confirmado não é tocado). Idempotente.
"""
import logging

from lxml import etree

from odoo import SUPERUSER_ID, api
from odoo.tools import file_open

_logger = logging.getLogger(__name__)

ANTIGA_1_10_ART_480 = r"""
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
    - ADIANTAMENTO_13
)
result = tools.br.round_money(max(min(devido, disponivel - DESCONTO_AVISO_PREVIO, remuneracao - DESCONTO_AVISO_PREVIO), 0))
        """

ANTIGA_1_11_ART_480 = r"""
media = tools.br.media_habitual(payslip._l10n_br_codes_media_habitual())
remuneracao = contract.wage + media + tools.br.adicionais_fixos(contract)
devido = tools.br.round_money(payslip._l10n_br_desconto_art_480(remuneracao))
# Não pode deixar o líquido negativo: só o que sobra dos créditos depois dos
# descontos obrigatórios e do aviso não cumprido. Teto de um mês de remuneração
# para o conjunto das compensações (art. 477, §5º). O que não couber vai à
# linha informativa NAO_DESCONTADO_ART_480.
disponivel = (
    SALDO_SALARIO + DECIMO_RESCISAO + DECIMO_AVISO_INDENIZADO + FERIAS_INDENIZADAS
    + ADICIONAL_FERIAS_INDENIZADAS + FERIAS_VENCIDAS + ADICIONAL_FERIAS_VENCIDAS
    + AVISO_PREVIO_INDENIZADO + INDENIZACAO_ART_479
    - INSS - INSS_13 - IRRF - IRRF_13 - PENSAO_ALIMENTICIA - PENSAO_ALIMENTICIA_13
    - ADIANTAMENTO_13
)
result = tools.br.round_money(max(min(devido, disponivel - DESCONTO_AVISO_PREVIO, remuneracao - DESCONTO_AVISO_PREVIO), 0))
        """

ANTIGA_1_10_AVISO_PREVIO = r"""
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
    - ADIANTAMENTO_13
)
result = tools.br.round_money(max(min(devido, disponivel, remuneracao), 0))
        """

ANTIGA_1_11_AVISO_PREVIO = r"""
# Súmula 94 TST: a base soma a média das verbas habituais.
media = tools.br.media_habitual(payslip._l10n_br_codes_media_habitual())
remuneracao = contract.wage + media + tools.br.adicionais_fixos(contract)
devido = tools.br.round_money(remuneracao)
# Não pode deixar o líquido negativo nem passar de um mês de remuneração (art.
# 477, §5º): desconta só o que sobra dos créditos depois dos descontos
# obrigatórios. O restante vai à linha informativa NAO_DESCONTADO_AVISO_PREVIO.
disponivel = (
    SALDO_SALARIO + DECIMO_RESCISAO + DECIMO_AVISO_INDENIZADO + FERIAS_INDENIZADAS
    + ADICIONAL_FERIAS_INDENIZADAS + FERIAS_VENCIDAS + ADICIONAL_FERIAS_VENCIDAS
    + AVISO_PREVIO_INDENIZADO + INDENIZACAO_ART_479
    - INSS - INSS_13 - IRRF - IRRF_13 - PENSAO_ALIMENTICIA - PENSAO_ALIMENTICIA_13
    - ADIANTAMENTO_13
)
result = tools.br.round_money(max(min(devido, disponivel, remuneracao), 0))
        """

ANTIGA_1_10_13_EXCESSO = r"""
media = tools.br.media_habitual(payslip._l10n_br_codes_media_habitual())
remuneracao = contract.wage + media + tools.br.adicionais_fixos(contract)
compensado = ADIANTAMENTO_13 + DESCONTO_AVISO_PREVIO + DESCONTO_ART_480
disponivel = (
    SALDO_SALARIO + DECIMO_RESCISAO + FERIAS_INDENIZADAS
    + ADICIONAL_FERIAS_INDENIZADAS + FERIAS_VENCIDAS + ADICIONAL_FERIAS_VENCIDAS
    + AVISO_PREVIO_INDENIZADO + INDENIZACAO_ART_479
    - INSS - INSS_13 - IRRF - IRRF_13 - PENSAO_ALIMENTICIA - PENSAO_ALIMENTICIA_13
    - compensado
)
# Maior desconto que cabe no teto do art. 477 §5º e no líquido, já contada a
# devolução exata do INSS e do IRRF (ver _l10n_br_desconto_excesso_13).
result = payslip._l10n_br_desconto_excesso_13(
    tools.br, contract, employee, DECIMO_DEVIDO, disponivel,
    remuneracao - compensado, PENSAO_ALIMENTICIA_13,
)
        """

ANTIGA_1_11_13_EXCESSO = r"""
media = tools.br.media_habitual(payslip._l10n_br_codes_media_habitual())
remuneracao = contract.wage + media + tools.br.adicionais_fixos(contract)
compensado = ADIANTAMENTO_13 + DESCONTO_AVISO_PREVIO + DESCONTO_ART_480
disponivel = (
    SALDO_SALARIO + DECIMO_RESCISAO + DECIMO_AVISO_INDENIZADO + FERIAS_INDENIZADAS
    + ADICIONAL_FERIAS_INDENIZADAS + FERIAS_VENCIDAS + ADICIONAL_FERIAS_VENCIDAS
    + AVISO_PREVIO_INDENIZADO + INDENIZACAO_ART_479
    - INSS - INSS_13 - IRRF - IRRF_13 - PENSAO_ALIMENTICIA - PENSAO_ALIMENTICIA_13
    - compensado
)
# Maior desconto que cabe no teto do art. 477 §5º e no líquido, já contada a
# devolução exata do INSS e do IRRF (ver _l10n_br_desconto_excesso_13).
result = payslip._l10n_br_desconto_excesso_13(
    tools.br, contract, employee, DECIMO_DEVIDO, disponivel,
    remuneracao - compensado, PENSAO_ALIMENTICIA_13,
)
        """

# xmlid: fórmulas gravadas pelas versões anteriores (a 1.10.0 e a 1.11.0)
REGRAS = {
    "hr_rule_desconto_art_480": (ANTIGA_1_10_ART_480, ANTIGA_1_11_ART_480),
    "hr_rule_desconto_aviso_previo": (
        ANTIGA_1_10_AVISO_PREVIO,
        ANTIGA_1_11_AVISO_PREVIO,
    ),
    "hr_rule_desconto_13_excesso": (
        ANTIGA_1_10_13_EXCESSO,
        ANTIGA_1_11_13_EXCESSO,
    ),
}
ARQUIVO = "hr_salary_rule_rescisao_data.xml"


def _valor_novo(xmlid):
    with file_open(f"l10n_br_hr_vacation/data/{ARQUIVO}", "rb") as arq:
        no = etree.parse(arq).xpath(
            f"//record[@id='{xmlid}']/field[@name='amount_python_compute']"
        )
    return no[0].text


def _normaliza(texto):
    return "\n".join(
        linha.rstrip()
        for linha in (texto or "").replace("\r\n", "\n").strip().splitlines()
    )


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    for xmlid, antigas in REGRAS.items():
        regra = env.ref(f"l10n_br_hr_vacation.{xmlid}", raise_if_not_found=False)
        if not regra:
            continue
        novo = _valor_novo(xmlid)
        atual = _normaliza(regra.amount_python_compute)
        if atual == _normaliza(novo):
            _logger.info("TG-151: %s já atualizada", xmlid)
        elif atual in {_normaliza(antiga) for antiga in antigas}:
            regra.write({"amount_python_compute": novo})
            _logger.info("TG-151: %s atualizada para a fórmula atual", regra.code)
        else:
            _logger.warning(
                "TG-151: a regra de desconto '%s' (%s) está personalizada e não foi "
                "atualizada. Compare com l10n_br_hr_vacation/data/%s: o "
                "'disponível' deve somar DECIMO_AVISO_INDENIZADO (TG-136) e a "
                "remuneração deve usar tools.br.adicionais_fixos(contract, "
                "'momento') (TG-133).",
                regra.name,
                xmlid,
                ARQUIVO,
            )
