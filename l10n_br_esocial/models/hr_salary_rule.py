# Copyright 2024 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

# Tabelas de incidência do leiaute S-1.3 do eSocial (NT 07/2026 rev. 20/10/2026):
# códigos de ``codIncCP``, ``codIncIRRF`` (Tabela 21, só os vigentes) e ``codIncFGTS``.
# A cópia oficial usada pelo teste está em ``tests/leiaute_s13.py``.

# Incidência INSS (Contribuição Previdenciária) - S-1010 codIncCP
ESOCIAL_COD_INC_CP = [
    ("00", "00 - Não é base de cálculo"),
    (
        "01",
        "01 - Não é base de cálculo em função de acordos internacionais de previdência social",  # noqa: B950
    ),
    (
        "11",
        "11 - Base de cálculo das contribuições sociais - Salário de contribuição - Mensal",  # noqa: B950
    ),
    (
        "12",
        "12 - Base de cálculo das contribuições sociais - Salário de contribuição - 13º salário",  # noqa: B950
    ),
    (
        "13",
        "13 - Base de cálculo das contribuições sociais - Salário de contribuição - Exclusiva do empregador - Mensal",  # noqa: B950
    ),
    (
        "14",
        "14 - Base de cálculo das contribuições sociais - Salário de contribuição - Exclusiva do empregador - 13° salário",  # noqa: B950
    ),
    (
        "15",
        "15 - Base de cálculo das contribuições sociais - Salário de contribuição - Exclusiva do segurado - Mensal",  # noqa: B950
    ),
    (
        "16",
        "16 - Base de cálculo das contribuições sociais - Salário de contribuição - Exclusiva do segurado - 13° salário",  # noqa: B950
    ),
    (
        "21",
        "21 - Base de cálculo das contribuições sociais - Salário de contribuição - Salário-maternidade mensal, pago pelo empregador",  # noqa: B950
    ),
    (
        "22",
        "22 - Base de cálculo das contribuições sociais - Salário de contribuição - Salário-maternidade 13º salário, pago pelo empregador",  # noqa: B950
    ),
    (
        "23",
        "23 - Base de cálculo das contribuições sociais - Salário de contribuição - Salário-paternidade mensal, pago pelo empregador",  # noqa: B950
    ),
    (
        "24",
        "24 - Base de cálculo das contribuições sociais - Salário de contribuição - Salário-paternidade 13º salário, pago pelo empregador",  # noqa: B950
    ),
    (
        "25",
        "25 - Base de cálculo das contribuições sociais - Salário de contribuição - Salário-maternidade mensal, pago pelo INSS",  # noqa: B950
    ),
    (
        "26",
        "26 - Base de cálculo das contribuições sociais - Salário de contribuição - Salário-maternidade 13° salário, pago pelo INSS",  # noqa: B950
    ),
    (
        "27",
        "27 - Base de cálculo das contribuições sociais - Salário de contribuição - Salário-paternidade mensal, pago pelo INSS",  # noqa: B950
    ),
    (
        "28",
        "28 - Base de cálculo das contribuições sociais - Salário de contribuição - Salário-paternidade 13° salário, pago pelo INSS",  # noqa: B950
    ),
    (
        "31",
        "31 - Contribuição descontada do segurado sobre salário de contribuição - Mensal",  # noqa: B950
    ),
    (
        "32",
        "32 - Contribuição descontada do segurado sobre salário de contribuição - 13º salário",  # noqa: B950
    ),
    (
        "34",
        "34 - Contribuição descontada do segurado sobre salário de contribuição - SEST",
    ),
    (
        "35",
        "35 - Contribuição descontada do segurado sobre salário de contribuição - SENAT",  # noqa: B950
    ),
    ("51", "51 - Outros - Salário-família"),
    (
        "91",
        "91 - Suspensão de incidência sobre salário de contribuição em decorrência de decisão judicial - Mensal",  # noqa: B950
    ),
    (
        "92",
        "92 - Suspensão de incidência sobre salário de contribuição em decorrência de decisão judicial - 13º salário",  # noqa: B950
    ),
    (
        "93",
        "93 - Suspensão de incidência sobre salário de contribuição em decorrência de decisão judicial - Salário-maternidade",  # noqa: B950
    ),
    (
        "94",
        "94 - Suspensão de incidência sobre salário de contribuição em decorrência de decisão judicial - Salário-maternidade 13º salário",  # noqa: B950
    ),
    (
        "95",
        "95 - Suspensão de incidência sobre salário de contribuição em decorrência de decisão judicial - Exclusiva do empregador - Mensal",  # noqa: B950
    ),
    (
        "96",
        "96 - Suspensão de incidência sobre salário de contribuição em decorrência de decisão judicial - Exclusiva do empregador - 13º salário",  # noqa: B950
    ),
    (
        "97",
        "97 - Suspensão de incidência sobre salário de contribuição em decorrência de decisão judicial - Exclusiva do empregador - Salário-maternidade",  # noqa: B950
    ),
    (
        "98",
        "98 - Suspensão de incidência sobre salário de contribuição em decorrência de decisão judicial - Exclusiva do empregador - Salário-maternidade 13º salário",  # noqa: B950
    ),
]

# Incidência IRRF - S-1010 codIncIRRF (Tabela 21; 0, 1, 15, 35, 44, 55, 78 e 81 a 95 expiraram)
ESOCIAL_COD_INC_IRRF = [
    (
        "09",
        "09 - Verba transitada pela folha de pagamento de natureza diversa de rendimento ou retenção/isenção/dedução de IR (exemplo: desconto de convênio farmácia, desconto de consignações, etc.)",  # noqa: B950
    ),
    ("11", "11 - Rendimento tributável (base de cálculo do IR) - Remuneração mensal"),
    ("12", "12 - Rendimento tributável (base de cálculo do IR) - 13º salário"),
    ("13", "13 - Rendimento tributável (base de cálculo do IR) - Férias"),
    ("14", "14 - Rendimento tributável (base de cálculo do IR) - PLR"),
    ("31", "31 - Retenção do IRRF efetuada sobre - Remuneração mensal"),
    ("32", "32 - Retenção do IRRF efetuada sobre - 13º salário"),
    ("33", "33 - Retenção do IRRF efetuada sobre - Férias"),
    ("34", "34 - Retenção do IRRF efetuada sobre - PLR"),
    (
        "41",
        "41 - Dedução do rendimento tributável do IRRF - Previdência Social Oficial - PSO - Remuneração mensal",  # noqa: B950
    ),
    ("42", "42 - Dedução do rendimento tributável do IRRF - PSO - 13º salário"),
    ("43", "43 - Dedução do rendimento tributável do IRRF - PSO - Férias"),
    (
        "46",
        "46 - Dedução do rendimento tributável do IRRF - Previdência complementar - Salário mensal",  # noqa: B950
    ),
    (
        "47",
        "47 - Dedução do rendimento tributável do IRRF - Previdência complementar - 13º salário",  # noqa: B950
    ),
    (
        "48",
        "48 - Dedução do rendimento tributável do IRRF - Previdência complementar - Férias",  # noqa: B950
    ),
    (
        "51",
        "51 - Dedução do rendimento tributável do IRRF - Pensão alimentícia - Remuneração mensal",  # noqa: B950
    ),
    (
        "52",
        "52 - Dedução do rendimento tributável do IRRF - Pensão alimentícia - 13º salário",  # noqa: B950
    ),
    (
        "53",
        "53 - Dedução do rendimento tributável do IRRF - Pensão alimentícia - Férias",
    ),
    ("54", "54 - Dedução do rendimento tributável do IRRF - Pensão alimentícia - PLR"),
    (
        "61",
        "61 - Dedução do rendimento tributável do IRRF - Fundo de Aposentadoria Programada Individual - FAPI - Remuneração mensal",  # noqa: B950
    ),
    (
        "62",
        "62 - Dedução do rendimento tributável do IRRF - Fundo de Aposentadoria Programada Individual - FAPI - 13º salário",  # noqa: B950
    ),
    (
        "63",
        "63 - Dedução do rendimento tributável do IRRF - Fundação de previdência complementar do servidor público - Remuneração mensal",  # noqa: B950
    ),
    (
        "64",
        "64 - Dedução do rendimento tributável do IRRF - Fundação de previdência complementar do servidor público - 13º salário",  # noqa: B950
    ),
    (
        "65",
        "65 - Dedução do rendimento tributável do IRRF - Fundação de previdência complementar do servidor público - Férias",  # noqa: B950
    ),
    (
        "66",
        "66 - Dedução do rendimento tributável do IRRF - Fundo de Aposentadoria Programada Individual - FAPI - Férias",  # noqa: B950
    ),
    (
        "68",
        "68 - Dedução do rendimento tributável do IRRF - Desconto simplificado mensal",
    ),
    (
        "67",
        "67 - Dedução do rendimento tributável para uso exclusivo na Declaração de Ajuste Anual - Plano privado coletivo de assistência à saúde",  # noqa: B950
    ),
    (
        "70",
        "70 - Rendimento não tributável ou isento do IRRF - Parcela isenta 65 anos - Remuneração mensal",  # noqa: B950
    ),
    (
        "71",
        "71 - Rendimento não tributável ou isento do IRRF - Parcela isenta 65 anos - 13º salário",  # noqa: B950
    ),
    ("72", "72 - Rendimento não tributável ou isento do IRRF - Diárias"),
    ("73", "73 - Rendimento não tributável ou isento do IRRF - Ajuda de custo"),
    (
        "74",
        "74 - Rendimento não tributável ou isento do IRRF - Indenização e rescisão de contrato, inclusive a título de PDV e acidentes de trabalho",  # noqa: B950
    ),
    ("75", "75 - Rendimento não tributável ou isento do IRRF - Abono pecuniário"),
    (
        "76",
        "76 - Rendimento não tributável ou isento do IRRF - Rendimento de beneficiário com moléstia grave ou acidente em serviço - Remuneração mensal",  # noqa: B950
    ),
    (
        "77",
        "77 - Rendimento não tributável ou isento do IRRF - Rendimento de beneficiário com moléstia grave ou acidente em serviço - 13º salário",  # noqa: B950
    ),
    ("700", "700 - Rendimento não tributável ou isento do IRRF - Auxílio moradia"),
    (
        "701",
        "701 - Rendimento não tributável ou isento do IRRF - Parte não tributável do valor de serviço de transporte de passageiros ou cargas",  # noqa: B950
    ),
    (
        "702",
        "702 - Rendimento não tributável ou isento do IRRF - Bolsa médico residente - remuneração mensal",  # noqa: B950
    ),
    (
        "703",
        "703 - Rendimento não tributável ou isento do IRRF - Bolsa médico residente - 13º salário",  # noqa: B950
    ),
    (
        "704",
        "704 - Rendimento não tributável ou isento do IRRF - Juros de mora recebidos, devidos pelo atraso no pagamento de remuneração por exercício de emprego, cargo ou função",  # noqa: B950
    ),
    (
        "79",
        "79 - Rendimento não tributável ou isento do IRRF - Outras isenções (o nome da rubrica deve ser claro para identificação da natureza dos valores)",  # noqa: B950
    ),
    (
        "9011",
        "9011 - Exigibilidade suspensa - Rendimento tributável (base de cálculo do IR) - Remuneração mensal",  # noqa: B950
    ),
    (
        "9012",
        "9012 - Exigibilidade suspensa - Rendimento tributável (base de cálculo do IR) - 13º salário",  # noqa: B950
    ),
    (
        "9013",
        "9013 - Exigibilidade suspensa - Rendimento tributável (base de cálculo do IR) - Férias",  # noqa: B950
    ),
    (
        "9014",
        "9014 - Exigibilidade suspensa - Rendimento tributável (base de cálculo do IR) - PLR",  # noqa: B950
    ),
    (
        "9031",
        "9031 - Exigibilidade suspensa - Retenção do IRRF efetuada sobre - Remuneração mensal",  # noqa: B950
    ),
    (
        "9032",
        "9032 - Exigibilidade suspensa - Retenção do IRRF efetuada sobre - 13º salário",
    ),
    (
        "9033",
        "9033 - Exigibilidade suspensa - Retenção do IRRF efetuada sobre - Férias",
    ),
    ("9034", "9034 - Exigibilidade suspensa - Retenção do IRRF efetuada sobre - PLR"),
    (
        "9831",
        "9831 - Exigibilidade suspensa - Retenção do IRRF efetuada sobre - Depósito judicial - Mensal",  # noqa: B950
    ),
    (
        "9832",
        "9832 - Exigibilidade suspensa - Retenção do IRRF efetuada sobre - Depósito judicial - 13º salário",  # noqa: B950
    ),
    (
        "9833",
        "9833 - Exigibilidade suspensa - Retenção do IRRF efetuada sobre - Depósito judicial - Férias",  # noqa: B950
    ),
    (
        "9834",
        "9834 - Exigibilidade suspensa - Retenção do IRRF efetuada sobre - Depósito judicial - PLR",  # noqa: B950
    ),
    (
        "9041",
        "9041 - Exigibilidade suspensa - Dedução da base de cálculo do IRRF - Previdência Social Oficial - PSO - Remuneração mensal",  # noqa: B950
    ),
    (
        "9042",
        "9042 - Exigibilidade suspensa - Dedução da base de cálculo do IRRF - PSO - 13º salário",  # noqa: B950
    ),
    (
        "9043",
        "9043 - Exigibilidade suspensa - Dedução da base de cálculo do IRRF - PSO - Férias",  # noqa: B950
    ),
    (
        "9046",
        "9046 - Exigibilidade suspensa - Dedução da base de cálculo do IRRF - Previdência complementar - Salário mensal",  # noqa: B950
    ),
    (
        "9047",
        "9047 - Exigibilidade suspensa - Dedução da base de cálculo do IRRF - Previdência complementar - 13º salário",  # noqa: B950
    ),
    (
        "9048",
        "9048 - Exigibilidade suspensa - Dedução da base de cálculo do IRRF - Previdência complementar - Férias",  # noqa: B950
    ),
    (
        "9051",
        "9051 - Exigibilidade suspensa - Dedução da base de cálculo do IRRF - Pensão alimentícia - Remuneração mensal",  # noqa: B950
    ),
    (
        "9052",
        "9052 - Exigibilidade suspensa - Dedução da base de cálculo do IRRF - Pensão alimentícia - 13º salário",  # noqa: B950
    ),
    (
        "9053",
        "9053 - Exigibilidade suspensa - Dedução da base de cálculo do IRRF - Pensão alimentícia - Férias",  # noqa: B950
    ),
    (
        "9054",
        "9054 - Exigibilidade suspensa - Dedução da base de cálculo do IRRF - Pensão alimentícia - PLR",  # noqa: B950
    ),
    (
        "9061",
        "9061 - Exigibilidade suspensa - Dedução da base de cálculo do IRRF - Fundo de Aposentadoria Programada Individual - FAPI - Remuneração mensal",  # noqa: B950
    ),
    (
        "9062",
        "9062 - Exigibilidade suspensa - Dedução da base de cálculo do IRRF - Fundo de Aposentadoria Programada Individual - FAPI - 13º salário",  # noqa: B950
    ),
    (
        "9063",
        "9063 - Exigibilidade suspensa - Dedução da base de cálculo do IRRF - Fundação de previdência complementar do servidor público - Remuneração mensal",  # noqa: B950
    ),
    (
        "9064",
        "9064 - Exigibilidade suspensa - Dedução da base de cálculo do IRRF - Fundação de previdência complementar do servidor público - 13º salário",  # noqa: B950
    ),
    (
        "9065",
        "9065 - Exigibilidade suspensa - Dedução da base de cálculo do IRRF - Fundação de previdência complementar do servidor público - Férias",  # noqa: B950
    ),
    (
        "9066",
        "9066 - Exigibilidade suspensa - Dedução da base de cálculo do IRRF - Fundo de Aposentadoria Programada Individual - FAPI - Férias",  # noqa: B950
    ),
    (
        "9067",
        "9067 - Exigibilidade suspensa - Dedução da base de cálculo do IRRF - Plano privado coletivo de assistência à saúde",  # noqa: B950
    ),
    ("9082", "9082 - Compensação judicial - Compensação judicial do ano-calendário"),
    ("9083", "9083 - Compensação judicial - Compensação judicial de anos anteriores"),
]

# Incidência FGTS - S-1010 codIncFGTS
ESOCIAL_COD_INC_FGTS = [
    ("00", "00 - Não é base de cálculo do FGTS"),
    ("11", "11 - Base de cálculo do FGTS mensal"),
    ("12", "12 - Base de cálculo do FGTS 13° salário"),
    ("21", "21 - Base de cálculo do FGTS aviso prévio indenizado"),
    ("31", "31 - Desconto eConsignado"),
    ("91", "91 - Incidência suspensa em decorrência de decisão judicial - FGTS mensal"),
    (
        "92",
        "92 - Incidência suspensa em decorrência de decisão judicial - FGTS 13º salário",  # noqa: B950
    ),
    (
        "93",
        "93 - Incidência suspensa em decorrência de decisão judicial - FGTS aviso prévio indenizado",  # noqa: B950
    ),
]


# Tabela 21 (IRRF): códigos que expiraram em 30/06/2021 e já não saem do S-1010.
# O 00 "Rendimento não tributável" foi substituído, para o que não é base de IRRF,
# pelo 09 (verba de natureza diversa de rendimento, retenção, isenção ou dedução).
COD_INC_IRRF_EXPIRADOS = (
    "00",
    "01",
    "15",
    "35",
    "44",
    "55",
    "78",
    "81",
    "82",
    "83",
    "91",
    "92",
    "93",
    "94",
    "95",
)
COD_INC_IRRF_SEM_INCIDENCIA = "09"

# Incidência INSS de salário-maternidade (21/22: pago pelo empregador;
# 25/26: exclusiva do segurado). Rubrica com essa incidência é salário-maternidade
# e tem natureza própria (4050 mensal, 4051 13º), nunca a 1000 de salário comum.
COD_INC_CP_MATERNIDADE = ("21", "22", "25", "26")
NATUREZAS_SALARIO_COMUM = ("1000",)

# Campos que definem a rubrica no S-1010: regras com o mesmo código eSocial
# (férias, 13º e rescisão repetem o código da mensal) precisam concordar neles.
CAMPOS_DEFINICAO_RUBRICA = (
    "l10n_br_esocial_nat_rubr_id",
    "l10n_br_esocial_tp_rubr",
    "l10n_br_esocial_cod_inc_cp",
    "l10n_br_esocial_cod_inc_irrf",
    "l10n_br_esocial_cod_inc_fgts",
)


class HrSalaryRule(models.Model):
    _inherit = "hr.salary.rule"

    # Identificação da rubrica no eSocial
    l10n_br_esocial_cod_rubr = fields.Char(
        string="Código Rubrica eSocial",
        size=30,
        help="Código atribuído pelo empregador para a rubrica.",
    )
    l10n_br_esocial_ide_tab_rubr = fields.Char(
        string="ID Tabela Rubricas",
        size=8,
        help="Identificador da tabela de rubricas para diferenciação.",
    )
    l10n_br_esocial_nat_rubr_id = fields.Many2one(
        "l10n_br.esocial.natureza.rubrica",
        string="Natureza Rubrica (Tab. 3)",
        help="Natureza da rubrica conforme Tabela 3 do eSocial.",
    )
    l10n_br_esocial_tp_rubr = fields.Selection(
        [
            ("1", "1 - Vencimento/Provento"),
            ("2", "2 - Desconto"),
            ("3", "3 - Informativa"),
            ("4", "4 - Informativa Dedutora"),
        ],
        string="Tipo Rubrica",
        help="Tipo da rubrica conforme eSocial.",
    )

    # Incidências tributárias
    l10n_br_esocial_cod_inc_cp = fields.Selection(
        ESOCIAL_COD_INC_CP,
        string="Incidência INSS",
        help="Código de incidência tributária da rubrica para a Previdência Social.",
    )
    l10n_br_esocial_cod_inc_irrf = fields.Selection(
        ESOCIAL_COD_INC_IRRF,
        string="Incidência IRRF",
        help="Código de incidência tributária da rubrica para o IRRF.",
    )
    l10n_br_esocial_cod_inc_fgts = fields.Selection(
        ESOCIAL_COD_INC_FGTS,
        string="Incidência FGTS",
        help="Código de incidência tributária da rubrica para o FGTS.",
    )
    l10n_br_esocial_cod_inc_irrf_expirado = fields.Boolean(
        string="Incidência IRRF expirada",
        compute="_compute_l10n_br_esocial_cod_inc_irrf_expirado",
        search="_search_l10n_br_esocial_cod_inc_irrf_expirado",
        help="A regra guarda um código de IRRF que expirou na Tabela 21 do eSocial "
        "(ex.: 00). A tela não o oferece mais e o S-1010 não é gerado até a "
        "incidência ser escolhida de novo.",
    )

    @api.depends("l10n_br_esocial_cod_inc_irrf")
    def _compute_l10n_br_esocial_cod_inc_irrf_expirado(self):
        for rule in self:
            rule.l10n_br_esocial_cod_inc_irrf_expirado = (
                rule.l10n_br_esocial_cod_inc_irrf in COD_INC_IRRF_EXPIRADOS
            )

    def _search_l10n_br_esocial_cod_inc_irrf_expirado(self, operator, value):
        if operator not in ("=", "!="):
            raise UserError(_("Operador não suportado: %s", operator))
        expirado = bool(value) == (operator == "=")
        return [
            (
                "l10n_br_esocial_cod_inc_irrf",
                "in" if expirado else "not in",
                list(COD_INC_IRRF_EXPIRADOS),
            )
        ]

    def _esocial_cod_inc_irrf_s1010(self):
        """``codIncIRRF`` do S-1010: o da regra; sem incidência, o 09 vigente.

        Código expirado na Tabela 21 recusa a geração: o governo rejeita o evento e
        trocar por outro código muda o tratamento fiscal, decisão da folha.
        """
        self.ensure_one()
        codigo = self.l10n_br_esocial_cod_inc_irrf
        if not codigo:
            return COD_INC_IRRF_SEM_INCIDENCIA
        if codigo in COD_INC_IRRF_EXPIRADOS:
            raise UserError(
                _(
                    "A regra '%(regra)s' tem incidência de IRRF %(codigo)s, que "
                    "expirou na Tabela 21 do eSocial. Escolha a incidência vigente na "
                    "aba eSocial da regra (para o que não é rendimento, retenção ou "
                    "dedução de IRRF, a 09).",
                    regra=self.display_name,
                    codigo=codigo,
                )
            )
        return codigo

    def _esocial_irrf_vencimento_sem_escolha(self):
        """Regras de vencimento (``tpRubr`` 1) com a incidência de IRRF em branco.

        Em vencimento, o 09 ("verba de natureza diversa de rendimento") tira o
        rendimento da base de IRRF e o governo aceita o evento sem aviso; por isso
        a escolha tem de ser explícita. Desconto e informativa seguem com o 09.
        """
        return self.filtered(
            lambda r: r.l10n_br_esocial_tp_rubr == "1"
            and not r.l10n_br_esocial_cod_inc_irrf
        )

    def _esocial_check_irrf_vencimento(self):
        """Recusa, numa mensagem só, as regras de vencimento sem incidência de IRRF."""
        pendentes = self._esocial_irrf_vencimento_sem_escolha()
        if not pendentes:
            return
        raise UserError(
            _(
                "Regra de vencimento (tipo de rubrica 1) sem Incidência IRRF: o "
                "S-1010 não é gerado até a escolha explícita. Preencha a "
                "Incidência IRRF na aba eSocial de cada regra: 11 a 14 se o "
                "rendimento é tributável, 70 a 79 ou 700 a 704 se é isento, ou 09 "
                "se não é rendimento de IRRF. Regras: %s.",
                ", ".join(
                    f"'{r.display_name}' ({r.l10n_br_esocial_cod_rubr or r.code})"
                    for r in pendentes
                ),
            )
        )

    def _esocial_chave_rubrica(self):
        """Chave da rubrica no S-1010: (código, ID da tabela de rubricas)."""
        self.ensure_one()
        return (
            self.l10n_br_esocial_cod_rubr,
            self.l10n_br_esocial_ide_tab_rubr or "1",
        )

    def _esocial_definicao_rubrica(self):
        self.ensure_one()
        return (
            self.l10n_br_esocial_nat_rubr_id.id,
            self.l10n_br_esocial_tp_rubr or False,
            self.l10n_br_esocial_cod_inc_cp or False,
            self.l10n_br_esocial_cod_inc_irrf or COD_INC_IRRF_SEM_INCIDENCIA,
            self.l10n_br_esocial_cod_inc_fgts or False,
        )

    @api.constrains(
        "l10n_br_esocial_cod_rubr",
        "l10n_br_esocial_ide_tab_rubr",
        "active",
        "company_id",
        *CAMPOS_DEFINICAO_RUBRICA,
    )
    def _check_esocial_rubrica_unica(self):
        """Um código de rubrica eSocial tem uma só definição por empregador.

        O S-1010 declara cada código uma vez; duas regras com o mesmo código e
        natureza ou incidências diferentes não cabem na mesma rubrica. Regras
        de empresas diferentes são independentes; regra sem empresa vale para
        todas.
        """
        for rule in self.filtered(lambda r: r.active and r.l10n_br_esocial_cod_rubr):
            chave = rule._esocial_chave_rubrica()
            outras = self.search(
                [
                    ("id", "!=", rule.id),
                    ("l10n_br_esocial_cod_rubr", "=", chave[0]),
                ]
            ).filtered(
                lambda r, chave=chave, rule=rule: (
                    r._esocial_chave_rubrica() == chave
                    and (
                        not r.company_id
                        or not rule.company_id
                        or r.company_id == rule.company_id
                    )
                )
            )
            for outra in outras:
                if outra._esocial_definicao_rubrica() != (
                    rule._esocial_definicao_rubrica()
                ):
                    raise ValidationError(
                        _(
                            "O código de rubrica eSocial '%(cod)s' já é usado pela "
                            "regra '%(outra)s' com natureza ou incidências "
                            "diferentes das da regra '%(regra)s'. Use um código "
                            "único para cada rubrica."
                        )
                        % {
                            "cod": chave[0],
                            "outra": outra.display_name,
                            "regra": rule.display_name,
                        }
                    )
        # Mudar o código de uma regra com S-1010 pode repetir a chave de outro.
        self.env["l10n_br.esocial.s1010"].search(
            [("salary_rule_id", "in", self.ids)]
        )._check_rubrica_unica()

    @api.constrains("l10n_br_esocial_nat_rubr_id", "l10n_br_esocial_cod_inc_cp")
    def _check_esocial_natureza_maternidade(self):
        """Salário-maternidade não pode ir com a natureza de salário comum."""
        for rule in self:
            natureza = rule.l10n_br_esocial_nat_rubr_id
            if (
                natureza
                and natureza.codigo in NATUREZAS_SALARIO_COMUM
                and rule.l10n_br_esocial_cod_inc_cp in COD_INC_CP_MATERNIDADE
            ):
                raise ValidationError(
                    _(
                        "A regra '%(regra)s' tem incidência INSS de "
                        "salário-maternidade (%(inc)s) com a natureza "
                        "%(nat)s (salário comum). Use a natureza 4050 "
                        "(salário-maternidade) ou 4051 (13º)."
                    )
                    % {
                        "regra": rule.display_name,
                        "inc": rule.l10n_br_esocial_cod_inc_cp,
                        "nat": natureza.codigo,
                    }
                )

    @api.model
    def _esocial_tabela_rubricas_da_empresa(self, company=None):
        """ID da tabela de rubricas (``ideTabRubr``) que a ``company`` já usa.

        O mais frequente entre as regras da empresa (ou sem empresa) com código
        eSocial; ``"1"`` se ela ainda não configurou nenhuma. Regras de outras
        empresas não contam: cada empresa tem a sua tabela.
        """
        company = company or self.env.company
        grupos = self.sudo().read_group(
            [
                ("l10n_br_esocial_cod_rubr", "!=", False),
                ("l10n_br_esocial_ide_tab_rubr", "!=", False),
                ("company_id", "in", [False, company.id]),
            ],
            ["l10n_br_esocial_ide_tab_rubr"],
            ["l10n_br_esocial_ide_tab_rubr"],
        )
        if not grupos:
            return "1"
        melhor = max(grupos, key=lambda g: g["l10n_br_esocial_ide_tab_rubr_count"])
        return melhor["l10n_br_esocial_ide_tab_rubr"]

    @api.model
    def _esocial_configurar_salario_maternidade(self):
        """Configura no eSocial a rubrica ``SALARIO_MATERNIDADE`` do payroll.

        Natureza 4050 (salário-maternidade pago pelo empregador), incidência
        INSS 21 (compensada na guia), IRRF 11 e FGTS 11, como na rubrica padrão
        eSocial1700, na tabela de rubricas que a empresa já usa. Só preenche o
        que está vazio: o que a empresa já definiu fica como está. Nas empresas
        que já têm S-1010, cria o S-1010 da rubrica (um por rubrica, como em
        ``criar_para_regras``) com a validade do primeiro S-1010 da empresa, para
        a rubrica existir na tabela do governo antes do primeiro S-1200.
        Idempotente; chamada na instalação e na migração.
        """
        regra = self.env.ref(
            "l10n_br_hr_payroll.hr_rule_salario_maternidade", raise_if_not_found=False
        )
        natureza = self.env.ref(
            "l10n_br_esocial.nat_rubr_4050", raise_if_not_found=False
        )
        if not regra or not natureza:
            return False
        padrao = {
            "l10n_br_esocial_cod_rubr": "SAL_MATERNIDADE",
            "l10n_br_esocial_ide_tab_rubr": self._esocial_tabela_rubricas_da_empresa(
                regra.company_id
            ),
            "l10n_br_esocial_nat_rubr_id": natureza.id,
            "l10n_br_esocial_tp_rubr": "1",
            "l10n_br_esocial_cod_inc_cp": "21",
            "l10n_br_esocial_cod_inc_irrf": "11",
            "l10n_br_esocial_cod_inc_fgts": "11",
        }
        vals = {campo: valor for campo, valor in padrao.items() if not regra[campo]}
        if vals:
            regra.write(vals)
        S1010 = self.env["l10n_br.esocial.s1010"].sudo()
        for company in self.env["res.company"].sudo().search([]):
            primeiro = S1010.search(
                [("company_id", "=", company.id), ("operacao", "=", "inclusao")],
                order="ini_valid",
                limit=1,
            )
            if primeiro:
                S1010.with_company(company).criar_para_regras(regra, primeiro.ini_valid)
        return True
