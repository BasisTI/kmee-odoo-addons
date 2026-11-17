# Copyright 2026 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
# flake8: noqa: B950
"""TG-149: INSS mensal do aprendiz pela tabela progressiva, não 2%.

O 2% do aprendiz é só do FGTS (Lei 8.036/90, art. 15 §7º). O INSS do segurado
aprendiz (categoria 103) é o da tabela progressiva comum. A regra
``hr_rule_inss_aprendiz`` calculava 2% da base; agora a ``hr_rule_inss`` vale
para todos e a do aprendiz fica inativa.

As regras são ``noupdate="1"``: o ``-u`` não as troca em banco instalado. Aqui:

- ``hr_rule_inss`` perde a condição ``!= 'aprendiz'`` só se a condição e a
  fórmula gravadas forem exatamente as da 1.11.0 (copiadas dela, não do XML
  final);
- ``hr_rule_inss_aprendiz`` é desativada só se a condição e a fórmula forem as
  da 1.11.0 (2%) E a ``hr_rule_inss`` foi (ou já estava) atualizada. As duas
  trocas andam juntas: se uma regra está personalizada, a outra fica como está
  (senão o aprendiz ficaria sem INSS ou com INSS em dobro) e o aviso vai no log.

Depois da troca, as estruturas (``structure_clt`` e as personalizadas) perdem a
regra inativa do aprendiz; a que tinha só ela, sem a ``hr_rule_inss``, recebe a
``hr_rule_inss`` (senão o aprendiz ficaria sem INSS) e o log avisa.

Idempotente; holerites já calculados não mudam.
"""
import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)

CONDICAO_INSS_1_11 = "result = employee.l10n_br_tipo_contrato != 'aprendiz'"
FORMULA_INSS_1_11 = """base_inss = categories.GROSS - FALTAS - DESC_DSR
# Salário de contribuição da competência: soma o mensal e as férias gozadas no
# mês (Lei 8.212/91, art. 28); desconta o INSS já retido no recibo de férias.
base_ferias, inss_ferias = tools.br.inss_ferias_competencia(contract)
result = max(
    tools.br.calc_inss(max(base_inss, 0) + base_ferias) - inss_ferias, 0
)"""
CONDICAO_APRENDIZ_1_11 = "result = employee.l10n_br_tipo_contrato == 'aprendiz'"
FORMULA_APRENDIZ_1_11 = """base_inss = categories.GROSS - FALTAS - DESC_DSR
result = tools.br.round_money(max(base_inss, 0) * 0.02)"""


def _normaliza(texto):
    return "\n".join(
        linha.strip() for linha in (texto or "").strip().splitlines() if linha.strip()
    )


def _e_padrao_1_11(regra, condicao, formula):
    return (
        regra.condition_select == "python"
        and _normaliza(regra.condition_python) == _normaliza(condicao)
        and _normaliza(regra.amount_python_compute) == _normaliza(formula)
    )


def _ajusta_estruturas(env, comum, aprendiz):
    """Tira a regra inativa do aprendiz das estruturas; garante o INSS comum."""
    if not aprendiz:
        return
    estruturas = (
        env["hr.payroll.structure"]
        .with_context(active_test=False)
        .search([("rule_ids", "in", aprendiz.id)])
    )
    for estrutura in estruturas:
        comandos = [(3, aprendiz.id)]
        if comum not in estrutura.rule_ids:
            comandos.append((4, comum.id))
            _logger.warning(
                "TG-149: a estrutura '%s' tinha só a regra de INSS do aprendiz; "
                "foi incluída a hr_rule_inss (tabela progressiva), senão o "
                "aprendiz ficaria sem INSS.",
                estrutura.display_name,
            )
        estrutura.write({"rule_ids": comandos})


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    comum = env.ref("l10n_br_hr_payroll.hr_rule_inss", raise_if_not_found=False)
    aprendiz = env.ref(
        "l10n_br_hr_payroll.hr_rule_inss_aprendiz", raise_if_not_found=False
    )
    if not comum:
        return
    aprendiz_ativa = bool(aprendiz and aprendiz.active)
    if comum.condition_select == "none" and not aprendiz_ativa:
        _ajusta_estruturas(env, comum, aprendiz)
        _logger.info("TG-149: INSS do aprendiz já pela tabela comum")
        return
    comum_padrao = _e_padrao_1_11(comum, CONDICAO_INSS_1_11, FORMULA_INSS_1_11)
    aprendiz_padrao = not aprendiz_ativa or _e_padrao_1_11(
        aprendiz, CONDICAO_APRENDIZ_1_11, FORMULA_APRENDIZ_1_11
    )
    if not (comum_padrao and aprendiz_padrao):
        _logger.warning(
            "TG-149: a regra de INSS ('%s', hr_rule_inss) ou a do aprendiz "
            "('hr_rule_inss_aprendiz') está personalizada e NÃO foi atualizada. "
            "O INSS do aprendiz é o da tabela progressiva, não 2%% (o 2%% é só do "
            "FGTS): remova a condição de aprendiz da hr_rule_inss e desative a "
            "hr_rule_inss_aprendiz, ou ajuste a sua fórmula, para que o aprendiz "
            "tenha uma só regra de INSS.",
            comum.name,
        )
        return
    comum.condition_select = "none"
    if aprendiz_ativa:
        aprendiz.active = False
    _ajusta_estruturas(env, comum, aprendiz)
    _logger.info("TG-149: INSS do aprendiz passa à tabela progressiva (regra comum)")
