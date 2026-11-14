# Copyright 2026 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""TG-142: prazo determinado deixa de ser reconhecido pelo nome.

O tipo de contratação passa a ter o booleano ``l10n_br_prazo_determinado``.
Marca os tipos que já se chamam "Prazo Determinado" (o que o módulo reconhecia
até a 1.4.0), para o 617 não mudar em bancos instalados. Idempotente.
"""
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    cr.execute(
        """
        UPDATE hr_contract_type
           SET l10n_br_prazo_determinado = TRUE
         WHERE l10n_br_prazo_determinado IS NOT TRUE
           AND EXISTS (
                SELECT 1 FROM jsonb_each_text(name)
                 WHERE lower(btrim(value)) = 'prazo determinado')
        """
    )
    _logger.info(
        "TG-142: %s tipo(s) de contratação marcados como prazo determinado",
        cr.rowcount,
    )
