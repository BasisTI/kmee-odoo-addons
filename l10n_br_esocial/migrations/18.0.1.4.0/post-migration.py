# Copyright 2026 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

"""TG-106: renumera o ``tpPgto`` dos pagamentos do S-1210 para o domínio do S-1.3.

Antes da correção, os rótulos do módulo diziam 2 = S-1202, 3 = S-1207, 4 = S-2299 e
5 = S-2399; o evtPgtos.xsd do S-1.3 define 2 = S-2299, 3 = S-2399, 4 = S-1202 e
5 = S-1207. O módulo só gerava 1, então só registro criado à mão muda. Os valores
guardados seguiam o sentido antigo; aqui passam ao sentido do leiaute. XML já
gerado não é alterado: evento com ``tpPgto`` 2 a 5 já transmitido precisa ser
conferido pelo responsável.
"""

import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    cr.execute(
        """UPDATE l10n_br_esocial_s1210_pagamento
              SET tp_pgto = CASE tp_pgto
                  WHEN '2' THEN '4' WHEN '3' THEN '5'
                  WHEN '4' THEN '2' WHEN '5' THEN '3' END
            WHERE tp_pgto IN ('2', '3', '4', '5')"""
    )
    if cr.rowcount:
        _logger.warning(
            "l10n_br_esocial: %s pagamento(s) do S-1210 com tpPgto 2-5 foram "
            "renumerados para o domínio do leiaute S-1.3; confira os eventos "
            "já gerados com esses pagamentos.",
            cr.rowcount,
        )
