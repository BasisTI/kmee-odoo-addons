# Copyright 2026 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""TG-86: uma só rubrica ``DSR_HE``, a do ``l10n_br_hr_payroll``.

A rubrica própria deste módulo deixou de ser calculada, mas o REGISTRO fica
(``noupdate``, fora da estrutura): holerites antigos têm linhas que apontam para
ele e a chave estrangeira impede apagá-lo. Em banco atualizado a rubrica antiga
ainda está ligada à estrutura CLT; aqui a estrutura passa a usar a da folha, para
o banco atualizado calcular igual ao banco novo.

Se a folha ainda não foi atualizada (``-u`` só do ponto) a rubrica nova não
existe: nada muda, a estrutura continua com a antiga e a migração da folha
(18.0.1.5.0) faz a troca depois.
"""

import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    estrutura = env.ref("l10n_br_hr_payroll.structure_clt", raise_if_not_found=False)
    folha = env.ref("l10n_br_hr_payroll.hr_rule_dsr_he", raise_if_not_found=False)
    antiga = env.ref(
        "l10n_br_hr_payroll_attendance.hr_rule_dsr_he", raise_if_not_found=False
    )
    if not estrutura or not folha:
        return
    comandos = []
    if antiga and antiga in estrutura.rule_ids:
        comandos.append((3, antiga.id))
    if folha not in estrutura.rule_ids:
        comandos.append((4, folha.id))
    if comandos:
        estrutura.write({"rule_ids": comandos})
        _logger.info("TG-86: DSR_HE da estrutura CLT passa a ser o da folha")
