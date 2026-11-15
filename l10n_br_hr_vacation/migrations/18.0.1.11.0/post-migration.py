# Copyright 2026 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
# flake8: noqa: B950
"""TG-136: o 13º sobre o aviso prévio indenizado em rubrica própria.

Regras e estruturas são ``noupdate="1"``: o ``-u`` cria a regra nova
(``DECIMO_AVISO_INDENIZADO``), mas não a liga à estrutura da rescisão nem troca
a fórmula do ``DECIMO_RESCISAO`` nem o líquido em bancos instalados. Aqui a
fórmula do ``DECIMO_RESCISAO`` e o NET passam a usar a rubrica nova SOMENTE se
a gravada ainda for exatamente a da 1.10.0; se qualquer das duas estiver
personalizada, nada é atualizado e a regra nova NÃO é ligada à estrutura (o
líquido não divergiria das linhas), com aviso no log. As 4 regras de desconto
só ganham a rubrica no "disponível" (não mudam valor): uma personalizada é
pulada, com aviso, sem barrar a separação do 13º. Holerites já calculados não
mudam. Idempotente.
"""
import logging

from lxml import etree

from odoo import SUPERUSER_ID, api
from odoo.tools import file_open

_logger = logging.getLogger(__name__)

ANTIGO_DECIMO = r"""
# TG-97: o 13º que a 2ª parcela (ou o 13º integral) confirmada já quitou no
# ano não se paga de novo: só a diferença dos avos. A 1ª parcela (adiantamento)
# não entra aqui: sai como desconto próprio (ADIANTAMENTO_13). O que a 2ª
# parcela pagou ALÉM do devido não vira valor negativo: sai como desconto
# (DESCONTO_13_EXCESSO, TG-141).
quitado = payslip._l10n_br_decimo_pago_ano(contract)['quitado']
result = max(DECIMO_DEVIDO - quitado, 0.0)
"""

ANTIGO_NET = r"""
result = (
    SALDO_SALARIO
    + DECIMO_RESCISAO
    + FERIAS_INDENIZADAS
    + ADICIONAL_FERIAS_INDENIZADAS
    + FERIAS_VENCIDAS
    + ADICIONAL_FERIAS_VENCIDAS
    + AVISO_PREVIO_INDENIZADO
    + INDENIZACAO_ART_479
    + DEVOLUCAO_INSS_13
    + DEVOLUCAO_IRRF_13
    - DESCONTO_ART_480
    - DESCONTO_AVISO_PREVIO
    - DESCONTO_13_EXCESSO
    - ADIANTAMENTO_13
    - INSS
    - INSS_13
    - IRRF
    - IRRF_13
    - PENSAO_ALIMENTICIA
    - PENSAO_ALIMENTICIA_13
)
"""

# Regras de desconto cujo "disponível" ganhou a rubrica nova: o texto da 1.10.0
# é o atual sem ela.
DESCONTOS_DISPONIVEL = (
    "hr_rule_desconto_art_480",
    "hr_rule_desconto_adiantamento_13_rescisao",
    "hr_rule_desconto_aviso_previo",
    "hr_rule_desconto_13_excesso",
)
RUBRICA_NOVA = "DECIMO_RESCISAO + DECIMO_AVISO_INDENIZADO + "
RUBRICA_ANTIGA = "DECIMO_RESCISAO + "

CAMPOS = (
    ("hr_rule_decimo_rescisao", "hr_salary_rule_13_data.xml", ANTIGO_DECIMO),
    ("hr_rule_net_rescisao", "hr_salary_rule_rescisao_data.xml", ANTIGO_NET),
) + tuple(
    (xmlid, "hr_salary_rule_rescisao_data.xml", None) for xmlid in DESCONTOS_DISPONIVEL
)


def _valor_novo(arquivo, xmlid):
    with file_open(f"l10n_br_hr_vacation/data/{arquivo}", "rb") as arq:
        no = etree.parse(arq).xpath(
            f"//record[@id='{xmlid}']/field[@name='amount_python_compute']"
        )
    return no[0].text


def _normaliza(texto):
    return (texto or "").replace("\r\n", "\n").strip()


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    atualizar = []
    essenciais = {"hr_rule_decimo_rescisao", "hr_rule_net_rescisao"}
    for xmlid, arquivo, antigo in CAMPOS:
        regra = env.ref(f"l10n_br_hr_vacation.{xmlid}", raise_if_not_found=False)
        if not regra:
            continue
        novo = _valor_novo(arquivo, xmlid)
        if antigo is None:
            antigo = novo.replace(RUBRICA_NOVA, RUBRICA_ANTIGA)
        atual = _normaliza(regra.amount_python_compute)
        if atual == _normaliza(novo):
            _logger.info("TG-136: %s já atualizada", xmlid)
        elif atual == _normaliza(antigo):
            atualizar.append((regra, novo))
        elif xmlid not in essenciais:
            _logger.warning(
                "TG-136: a regra de desconto '%s' (%s) está personalizada: foi "
                "pulada (só o 'disponível' ganha DECIMO_AVISO_INDENIZADO). "
                "Inclua a rubrica nela, se usar o 'disponível'.",
                regra.name,
                xmlid,
            )
        else:
            _logger.warning(
                "TG-136: a regra '%s' (%s) está personalizada: NADA foi atualizado "
                "nem ligado à estrutura, para o líquido não divergir das linhas. "
                "Compare com l10n_br_hr_vacation/data/ (13º sobre o aviso "
                "indenizado em DECIMO_AVISO_INDENIZADO) e ajuste.",
                regra.name,
                xmlid,
            )
            return
    for regra, novo in atualizar:
        regra.write({"amount_python_compute": novo})
        _logger.info("TG-136: %s atualizada", regra.code)
    estrutura = env.ref(
        "l10n_br_hr_vacation.structure_rescisao", raise_if_not_found=False
    )
    nova = env.ref(
        "l10n_br_hr_vacation.hr_rule_decimo_aviso_indenizado",
        raise_if_not_found=False,
    )
    if estrutura and nova and nova not in estrutura.rule_ids:
        estrutura.write({"rule_ids": [(4, nova.id)]})
        _logger.info("TG-136: DECIMO_AVISO_INDENIZADO ligada à estrutura da rescisão")
