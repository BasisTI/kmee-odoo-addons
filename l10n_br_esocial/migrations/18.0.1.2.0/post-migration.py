# Copyright 2026 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

"""Sinaliza regras com código de incidência que saiu do leiaute S-1.3 (TG-107).

As listas de ``codIncCP``, ``codIncIRRF`` e ``codIncFGTS`` foram trocadas pelas do
leiaute S-1.3. No INSS e no FGTS só entraram códigos; no IRRF saíram 00, 01, 15, 35,
44, 55, 56, 81 a 83 e 91 a 95 (expirados ou inexistentes na Tabela 21) e vários
códigos mantidos mudaram de significado (o 52, por exemplo, era "diárias" e é pensão
alimentícia 13º salário). Não há como trocar um código por outro sem decisão da folha:
a migração **não altera** nenhuma regra, só registra no log as regras que ficaram com
valor fora da lista, para o responsável revisar antes de gerar o S-1010.
"""

import logging

_logger = logging.getLogger(__name__)

VALIDOS = {
    "l10n_br_esocial_cod_inc_cp": set(
        """
        00 01 11 12 13 14 15 16 21 22 23 24 25 26 27 28 31 32 34 35 51 91 92
        93 94 95 96 97 98
        """.split()
    ),
    "l10n_br_esocial_cod_inc_fgts": set(
        """
        00 11 12 21 31 91 92 93
        """.split()
    ),
    "l10n_br_esocial_cod_inc_irrf": set(
        """
        09 11 12 13 14 31 32 33 34 41 42 43 46 47 48 51 52 53 54 61 62 63 64
        65 66 67 68 70 71 72 73 74 75 76 77 79 700 701 702 703 704 9011 9012
        9013 9014 9031 9032 9033 9034 9041 9042 9043 9046 9047 9048 9051 9052
        9053 9054 9061 9062 9063 9064 9065 9066 9067 9082 9083 9831 9832 9833
        9834
        """.split()
    ),
}


def migrate(cr, version):
    if not version:
        return
    for coluna, validos in VALIDOS.items():
        cr.execute(
            f"""
            SELECT id, code, {coluna} FROM hr_salary_rule
            WHERE {coluna} IS NOT NULL AND {coluna} NOT IN %s
            """,  # noqa: S608 - nome de coluna fixo, vindo do dicionário acima
            (tuple(sorted(validos)),),
        )
        for regra_id, codigo, valor in cr.fetchall():
            _logger.warning(
                "eSocial: a regra %s (id %s) tem %s=%r, que não consta mais do "
                "leiaute S-1.3; revise antes de gerar o S-1010.",
                codigo,
                regra_id,
                coluna,
                valor,
            )
