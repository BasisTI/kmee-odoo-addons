# Copyright 2026 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
# flake8: noqa: B950
"""TG-133: periculosidade e insalubridade pela letra do art. 142 § 6º.

As regras são ``noupdate="1"``: o ``-u`` não troca a fórmula de bancos
instalados. Cada regra que chama ``tools.br.adicionais_fixos(contract)`` passa a
dizer de qual verba é (``ferias``, ``ferias_proporcionais``, ``13`` ou
``momento``): a chamada antiga é trocada pela nova, mesmo em fórmula
personalizada (só esse trecho muda, o resto fica). As férias vencidas, que
passam a usar o período aquisitivo de cada alocação, só trocam a fórmula se a
gravada ainda for exatamente a da 1.11.0; personalizada fica como está, com
aviso. Holerites já calculados não mudam. Idempotente.
"""
import logging

from lxml import etree

from odoo import SUPERUSER_ID, api
from odoo.tools import file_open

_logger = logging.getLogger(__name__)

CHAMADA_ANTIGA = "tools.br.adicionais_fixos(contract)"

VERBAS = {
    "hr_rule_adiantamento_13": "13",
    "hr_rule_decimo_bruto": "13",
    "hr_rule_decimo_devido": "13",
    "hr_rule_decimo_rescisao": "13",
    "hr_rule_ferias": "ferias",
    "hr_rule_abono_pecuniario": "ferias",
    "hr_rule_ferias_indenizadas": "ferias_proporcionais",
    "hr_rule_aviso_previo_indenizado": "momento",
    "hr_rule_indenizacao_art_479": "momento",
    "hr_rule_desconto_art_480": "momento",
    "hr_rule_desconto_aviso_previo": "momento",
    "hr_rule_nao_descontado_aviso_previo": "momento",
    "hr_rule_nao_descontado_art_480": "momento",
    "hr_rule_desconto_13_excesso": "momento",
}

VENCIDAS_XMLID = "hr_rule_ferias_vencidas"
VENCIDAS_ARQUIVO = "hr_salary_rule_rescisao_data.xml"
VENCIDAS_ANTIGA = """
# RF-18: também soma a média habitual, como qualquer verba de férias.
media = tools.br.media_habitual(payslip._l10n_br_codes_media_habitual())
salario_dia = (contract.wage + media + tools.br.adicionais_fixos(contract)) / 30
result = tools.br.round_money(sum(
    salario_dia * periodo["dias"] * (2 if periodo["dobro"] else 1)
    for periodo in payslip._l10n_br_ferias_vencidas_dados()
))
        """


def _normaliza(texto):
    return "\n".join(linha.rstrip() for linha in (texto or "").strip().splitlines())


def _valor_novo(arquivo, xmlid):
    with file_open(f"l10n_br_hr_vacation/data/{arquivo}", "rb") as f:
        arvore = etree.parse(f)
    campo = arvore.xpath(
        f"//record[@id='{xmlid}']/field[@name='amount_python_compute']"
    )
    return campo[0].text if campo else None


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    for xmlid, verba in VERBAS.items():
        regra = env.ref(f"l10n_br_hr_vacation.{xmlid}", raise_if_not_found=False)
        if not regra:
            continue
        formula = regra.amount_python_compute or ""
        if CHAMADA_ANTIGA not in formula:
            _logger.info("TG-133: %s já atualizada", xmlid)
            continue
        regra.amount_python_compute = formula.replace(
            CHAMADA_ANTIGA, f"tools.br.adicionais_fixos(contract, '{verba}')"
        )
        _logger.info("TG-133: %s passa a usar a verba %s", regra.code, verba)
    regra = env.ref(f"l10n_br_hr_vacation.{VENCIDAS_XMLID}", raise_if_not_found=False)
    if not regra:
        return
    novo = _valor_novo(VENCIDAS_ARQUIVO, VENCIDAS_XMLID)
    atual = _normaliza(regra.amount_python_compute)
    if atual == _normaliza(novo):
        _logger.info("TG-133: %s já atualizada", VENCIDAS_XMLID)
    elif atual == _normaliza(VENCIDAS_ANTIGA):
        regra.amount_python_compute = novo
        _logger.info("TG-133: FERIAS_VENCIDAS atualizada")
    else:
        _logger.warning(
            "TG-133: FERIAS_VENCIDAS está personalizada e não foi atualizada; "
            "o adicional fixo dela segue a chamada antiga "
            "(tools.br.adicionais_fixos(contract)), sem a média do período "
            "aquisitivo de cada alocação."
        )
