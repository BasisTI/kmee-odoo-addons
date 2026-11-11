# Copyright 2024 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""TG-86: reflexo das horas extras e do adicional noturno no DSR.

As rubricas ``DSR_HE`` e ``DSR_NOTURNO`` são registros novos e o XML as cria,
mas a estrutura CLT é ``noupdate``: ligá-las a ela é feito aqui. Idempotente, e
sem mexer na estrutura que já tem uma rubrica com o mesmo código (por exemplo,
o ``DSR_HE`` do ``l10n_br_hr_payroll_attendance``, que apura pelo ponto).
"""

import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)

REGRAS = ("hr_rule_dsr_he", "hr_rule_dsr_noturno")


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    estrutura = env.ref("l10n_br_hr_payroll.structure_clt", raise_if_not_found=False)
    if not estrutura:
        return
    codigos = set(estrutura.rule_ids.mapped("code"))
    for xmlid in REGRAS:
        regra = env.ref(f"l10n_br_hr_payroll.{xmlid}", raise_if_not_found=False)
        if not regra or regra.code in codigos:
            continue
        estrutura.write({"rule_ids": [(4, regra.id)]})
        _logger.info("TG-86: %s ligada à estrutura CLT", regra.code)
