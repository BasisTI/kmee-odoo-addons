# Copyright 2026 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

"""Regras de vencimento sem incidência de IRRF (TG-131).

Desde a TG-125 a regra sem incidência de IRRF saía no S-1010 com o 09, o que, num
vencimento, tira o rendimento da base de IRRF sem aviso. Agora a geração do S-1010
de regra de vencimento (``tpRubr`` 1) sem incidência de IRRF é recusada até a folha
escolher o código. A migração **não altera** nenhuma regra (a escolha é fiscal);
só lista no log as regras que vão ser recusadas, de uma vez.
"""

import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return
    cr.execute(
        """
        SELECT id, code FROM hr_salary_rule
        WHERE l10n_br_esocial_tp_rubr = '1'
          AND COALESCE(l10n_br_esocial_cod_inc_irrf, '') = ''
          AND COALESCE(l10n_br_esocial_cod_rubr, '') != ''
        ORDER BY id
        """
    )
    regras = cr.fetchall()
    if regras:
        _logger.warning(
            "eSocial: %d regra(s) de vencimento sem Incidência IRRF; o S-1010 será "
            "recusado até a escolha (11 a 14 tributável, 70 a 79 e 700 a 704 "
            "isento, ou 09): %s",
            len(regras),
            ", ".join(f"{codigo} (id {regra_id})" for regra_id, codigo in regras),
        )
