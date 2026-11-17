# Copyright 2026 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""TG-148: contas do FGTS de férias, 13º e rescisão em banco já instalado.

O ``post_init_hook`` só roda na instalação; um banco que já tem o módulo não
ganharia as contas das regras de FGTS do ``l10n_br_hr_vacation``. A rotina é
idempotente e só preenche campo vazio (não sobrescreve conta configurada à
mão); regra ausente (módulo de férias não instalado) é ignorada.
"""
from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    env["hr.salary.rule"]._l10n_br_setup_payroll_accounts()
