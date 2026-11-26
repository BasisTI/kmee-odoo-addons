# Copyright 2026 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""TG-168: avisa os contratos com unidade do salário não suportada.

A 18.0.1.15.0 (TG-166) só listava os contratos Hourly sem valor da hora. Banco já
na 1.15.0 ou mais não a roda de novo: esta repete o WARNING para as unidades
diária, semanal, quinzenal, tarefa e não aplicável. Não altera dado; idempotente.
"""
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    cr.execute(
        """
        SELECT c.id FROM hr_contract c
          JOIN hr_contract_salary_unit u ON u.id = c.salary_unit
         WHERE u.code IN ('2', '3', '4', '6', '7')
         ORDER BY c.id
        """
    )
    ids = [r[0] for r in cr.fetchall()]
    if ids:
        _logger.warning(
            "TG-168: %d contrato(s) com a Unidade do Salário diária, semanal, "
            "quinzenal, por tarefa ou não aplicável (códigos 2, 3, 4, 6 e 7), "
            "ainda não suportadas: o holerite desses contratos é recusado até "
            "trocar a unidade para Hourly ou Monthly. Contratos: %s",
            len(ids),
            ids,
        )
