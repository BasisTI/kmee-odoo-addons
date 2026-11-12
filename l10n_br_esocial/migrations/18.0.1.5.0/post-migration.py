# Copyright 2026 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

"""Regras com incidência de IRRF expirada ou que mudou de rótulo (TG-125).

Complementa a migração 18.0.1.2.0 (TG-107):

* regra com ``codIncIRRF`` expirado na Tabela 21 (00, 01, 15, 35, 44, 55, 78, 81 a 83
  e 91 a 95) fica como está, mas passa a aparecer com aviso na aba eSocial e o S-1010
  recusa a geração até a folha escolher o código vigente;
* regra que usa um dos códigos mantidos que mudaram de rótulo (46, 51 a 54, 61, 71 a
  77, 79) é listada no log, pois quem escolheu pelo rótulo antigo pode ter declarado
  outra coisa (o 52, por exemplo, era "diárias" e é pensão alimentícia de 13º).
"""

import logging

_logger = logging.getLogger(__name__)

EXPIRADOS = ("00", "01", "15", "35", "44", "55", "78", "81", "82", "83") + tuple(
    f"9{n}" for n in range(1, 6)
)
ROTULO_TROCADO = (
    "46 51 52 53 54 61 71 72 73 74 75 76 77 79".split()
)  # fmt: skip


def _listar(cr, codigos):
    cr.execute(
        """
        SELECT id, code, l10n_br_esocial_cod_inc_irrf FROM hr_salary_rule
        WHERE l10n_br_esocial_cod_inc_irrf IN %s
        ORDER BY l10n_br_esocial_cod_inc_irrf, id
        """,
        (tuple(codigos),),
    )
    return cr.fetchall()


def migrate(cr, version):
    if not version:
        return
    for regra_id, codigo, valor in _listar(cr, EXPIRADOS):
        _logger.warning(
            "eSocial: a regra %s (id %s) tem incidência de IRRF %s, expirada na "
            "Tabela 21; escolha o código vigente antes de gerar o S-1010.",
            codigo,
            regra_id,
            valor,
        )
    for regra_id, codigo, valor in _listar(cr, ROTULO_TROCADO):
        _logger.warning(
            "eSocial: a regra %s (id %s) usa a incidência de IRRF %s, cujo rótulo "
            "mudou no leiaute S-1.3; confira se ainda é o que a regra pretende.",
            codigo,
            regra_id,
            valor,
        )
