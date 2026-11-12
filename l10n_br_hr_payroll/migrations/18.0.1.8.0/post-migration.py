# Copyright 2026 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""TG-87#P1: "CPP e RAT sobre o salário-maternidade" passa a vir desmarcado.

O padrão novo (STF, Tema 72) só vale para empresa nova. Em banco existente o
campo está marcado em todas as empresas, sem como separar quem o marcou de quem
só herdou o padrão antigo. Desmarca-se a empresa que ainda não tem holerite com
``SALARIO_MATERNIDADE`` (nada já calculado muda); a que tem fica como está, e a
mudança fica a cargo do DP, pelo campo da aba de encargos. Idempotente.
"""

import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    cr.execute(
        """UPDATE res_company c
              SET l10n_br_hr_patronal_sobre_salario_maternidade = FALSE
            WHERE l10n_br_hr_patronal_sobre_salario_maternidade IS TRUE
              AND NOT EXISTS (
                  SELECT 1
                    FROM hr_payslip_line l
                    JOIN hr_payslip p ON p.id = l.slip_id
                   WHERE l.code = 'SALARIO_MATERNIDADE'
                     AND p.state != 'cancel'
                     AND p.company_id = c.id)"""
    )
    _logger.info("TG-87#P1: %s empresa(s) com o novo padrão", cr.rowcount)
