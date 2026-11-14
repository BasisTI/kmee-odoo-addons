# Copyright 2026 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
# flake8: noqa: B950
"""TG-96: causas de rescisão (aviso, 13º, férias e multa por causa).

Regras e estruturas são ``noupdate="1"``: o ``-u`` cria as regras novas (arts.
479, 480 e 487 §2º), mas não as liga à estrutura da rescisão nem troca as
fórmulas em bancos instalados. Aqui as regras novas entram na estrutura e as
fórmulas e condições que passam a usar a tabela de causas são trocadas SOMENTE
se a gravada ainda for exatamente a da 1.7.0; regra personalizada fica como
está. Idempotente.
"""
import logging

from lxml import etree

from odoo import SUPERUSER_ID, api
from odoo.tools import file_open

_logger = logging.getLogger(__name__)

CAMPOS = {
    # (xmlid, campo): (arquivo, valor da 1.7.0)
    ("hr_rule_decimo_rescisao", "condition_python"): (
        "hr_salary_rule_13_data.xml",
        r"""
# RF-06: o 13º proporcional NÃO é devido na dispensa por JUSTA CAUSA
# (Lei 4.090/62 art. 3º: "ocorrendo rescisão, SEM justa causa..."; Decreto
# 57.155/65 art. 7º: "salvo na hipótese de rescisão com justa causa"). É
# devido em qualquer outra hipótese, inclusive pedido de demissão
# (Súmula 157 TST).
result = payslip.l10n_br_tipo_rescisao != 'justa_causa'
        """,
    ),
    ("hr_rule_decimo_rescisao", "amount_python_compute"): (
        "hr_salary_rule_13_data.xml",
        r"""
# RF-18: base soma a média de horas extras/adicional noturno habituais.
avos = payslip.l10n_br_avos_13
media = tools.br.media_habitual(payslip._l10n_br_codes_media_habitual())
result = tools.br.round_money((contract.wage + media + tools.br.adicionais_fixos(contract)) * avos / 12)
        """,
    ),
    ("hr_rule_ferias_indenizadas", "condition_python"): (
        "hr_salary_rule_rescisao_data.xml",
        r"""
result = (
    payslip.l10n_br_avos_ferias > 0
    and payslip.l10n_br_tipo_rescisao != 'justa_causa'
)
        """,
    ),
    ("hr_rule_ferias_indenizadas", "amount_python_compute"): (
        "hr_salary_rule_rescisao_data.xml",
        r"""
# RF-18: base soma a média de horas extras/adicional noturno habituais.
avos = payslip.l10n_br_avos_ferias
media = tools.br.media_habitual(payslip._l10n_br_codes_media_habitual())
result = tools.br.round_money((contract.wage + media + tools.br.adicionais_fixos(contract)) * avos / 12)
        """,
    ),
    ("hr_rule_adicional_ferias_indenizadas", "condition_python"): (
        "hr_salary_rule_rescisao_data.xml",
        r"""
result = (
    payslip.l10n_br_avos_ferias > 0
    and payslip.l10n_br_tipo_rescisao != 'justa_causa'
)
        """,
    ),
    ("hr_rule_aviso_previo_indenizado", "amount_python_compute"): (
        "hr_salary_rule_rescisao_data.xml",
        r"""
# Acordo (CLT art. 484-A, I, "a"): aviso pago pela METADE. Sem justa causa:
# integral. Súmula 94 TST: a base soma a média das verbas habituais.
dias = payslip._l10n_br_dias_aviso_previo()
media = tools.br.media_habitual(payslip._l10n_br_codes_media_habitual())
fator = 0.5 if payslip.l10n_br_tipo_rescisao == 'acordo' else 1.0
result = tools.br.round_money((contract.wage + media + tools.br.adicionais_fixos(contract)) / 30 * dias * fator)
        """,
    ),
    ("hr_rule_multa_fgts", "condition_python"): (
        "hr_salary_rule_rescisao_data.xml",
        r"""
result = payslip.l10n_br_tipo_rescisao in ('sem_justa_causa', 'acordo')
        """,
    ),
    ("hr_rule_multa_fgts", "amount_python_compute"): (
        "hr_salary_rule_rescisao_data.xml",
        r"""
if payslip.l10n_br_fgts_saldo_conta:
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
    + payslip._l10n_br_fgts_13_primeira_depositado(contract)
    + FGTS_AVISO
)
percentual = 0.20 if payslip.l10n_br_tipo_rescisao == 'acordo' else 0.40
result = tools.br.round_money((saldo + depositos) * percentual)
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
    "hr_rule_indenizacao_art_479",
    "hr_rule_desconto_art_480",
    "hr_rule_desconto_aviso_previo",
    "hr_rule_nao_descontado_aviso_previo",
    "hr_rule_nao_descontado_art_480",
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
            _logger.info("TG-96: %s.%s atualizado", xmlid, campo)
        elif _normaliza(regra[campo]) == _normaliza(_valor_novo(arquivo, xmlid, campo)):
            _logger.info("TG-96: %s.%s já atualizado", xmlid, campo)
        else:
            _logger.warning(
                "TG-96: a regra '%s' (%s) está personalizada e NÃO foi atualizada "
                "(campo %s). As causas de rescisão novas dependem da fórmula e "
                "da condição do módulo: revise a regra e compare com "
                "l10n_br_hr_vacation/data/ (sem isso, o valor pode sair errado "
                "em culpa recíproca, força maior, rescisão indireta e término "
                "de contrato a prazo).",
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
            _logger.info("TG-96: %s ligada à estrutura da rescisão", xmlid)
