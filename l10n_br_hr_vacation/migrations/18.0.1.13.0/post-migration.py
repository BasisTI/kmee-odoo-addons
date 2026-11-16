# Copyright 2026 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""TG-139: férias concedidas depois do concessivo, pagas em dobro (art. 137).

Regras e estruturas são ``noupdate="1"``: o ``-u`` cria as regras novas
(``FERIAS_DOBRO``, ``ADICIONAL_FERIAS_DOBRO``, ``ABONO_DOBRO`` e
``ADICIONAL_ABONO_DOBRO``), mas não as liga à estrutura de
férias de bancos instalados. Aqui elas entram na estrutura. Nenhuma fórmula
existente muda (o XML das regras da média, da TG-133, segue o mesmo): só o
recibo com gozo depois do concessivo passa a ter as linhas da dobra. Holerites já
calculados não mudam. Idempotente.
"""
import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    estrutura = env.ref(
        "l10n_br_hr_vacation.structure_ferias", raise_if_not_found=False
    )
    if not estrutura:
        return
    for xmlid in (
        "hr_rule_ferias_dobro",
        "hr_rule_adicional_ferias_dobro",
        "hr_rule_abono_dobro",
        "hr_rule_adicional_abono_dobro",
    ):
        regra = env.ref(f"l10n_br_hr_vacation.{xmlid}", raise_if_not_found=False)
        if regra and regra not in estrutura.rule_ids:
            estrutura.rule_ids = [(4, regra.id)]
            _logger.info("TG-139: %s ligada à estrutura de férias", regra.code)
