# Copyright 2026 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""TG-87: salário-maternidade com rubrica própria (um mecanismo só).

O S-1200 deixa de dividir o salário entre duas rubricas pelos dias de licença:
o holerite já traz o salário-maternidade na rubrica ``SALARIO_MATERNIDADE`` do
payroll. Esta migração:

- configura essa rubrica no eSocial (natureza 4050, incidências), sem alterar o
  que a empresa já tenha definido;
- registra no log as regras que tinham "Rubrica de Salário-Maternidade", campo
  que deixa de existir, e remove as colunas antigas (a marca do tipo de
  afastamento foi copiada pelo ``l10n_br_hr_payroll``).

Idempotente.
"""

import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def _coluna_existe(cr, tabela, coluna):
    cr.execute(
        """SELECT 1 FROM information_schema.columns
            WHERE table_name = %s AND column_name = %s""",
        (tabela, coluna),
    )
    return bool(cr.fetchone())


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    env["hr.salary.rule"]._esocial_configurar_salario_maternidade()
    if _coluna_existe(cr, "hr_salary_rule", "l10n_br_esocial_regra_maternidade_id"):
        cr.execute(
            """SELECT id, code FROM hr_salary_rule
                WHERE l10n_br_esocial_regra_maternidade_id IS NOT NULL"""
        )
        for regra_id, codigo in cr.fetchall():
            _logger.warning(
                "TG-87: a regra %s (id %s) tinha Rubrica de Salário-Maternidade; "
                "o vínculo foi removido: o salário-maternidade agora tem rubrica "
                "própria no holerite (SALARIO_MATERNIDADE).",
                codigo,
                regra_id,
            )
        cr.execute(
            "ALTER TABLE hr_salary_rule "
            "DROP COLUMN IF EXISTS l10n_br_esocial_regra_maternidade_id"
        )
    cr.execute(
        "ALTER TABLE hr_leave_type "
        "DROP COLUMN IF EXISTS l10n_br_esocial_salario_maternidade"
    )
