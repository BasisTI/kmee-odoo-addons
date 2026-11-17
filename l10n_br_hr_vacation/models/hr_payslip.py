# Copyright 2024 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import re
from datetime import date, timedelta

from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.tools import html_escape

from odoo.addons.l10n_br_hr_payroll.models import salary_rules_br

# Regras de cada tipo de rescisão (TG-96). ``mtv`` é o ``mtvDeslig`` do S-2299
# (tabela 19 do eSocial); ``aviso``, ``decimo`` e ``ferias`` são a fração devida
# do aviso prévio indenizado, do 13º e das férias proporcionais (+1/3); ``multa``
# é o percentual da multa do FGTS (Lei 8.036/90, art. 18, §§1º e 2º). As férias
# vencidas são devidas em qualquer causa (CLT art. 146, caput).
L10N_BR_REGRAS_RESCISAO = {
    # CLT art. 482: sem aviso, 13º, férias proporcionais nem multa.
    "justa_causa": {
        "mtv": "01",
        "aviso": 0.0,
        "decimo": 0.0,
        "ferias": 0.0,
        "multa": 0.0,
    },
    # Aviso integral, tudo devido e multa de 40%.
    "sem_justa_causa": {
        "mtv": "02",
        "aviso": 1.0,
        "decimo": 1.0,
        "ferias": 1.0,
        "multa": 0.40,
    },
    # Contrato a termo: art. 479 (empregador) e art. 480 (empregado), sem aviso.
    "antecipado_empregador": {
        "mtv": "03",
        "aviso": 0.0,
        "decimo": 1.0,
        "ferias": 1.0,
        "multa": 0.40,
    },
    "antecipado_empregado": {
        "mtv": "04",
        "aviso": 0.0,
        "decimo": 1.0,
        "ferias": 1.0,
        "multa": 0.0,
    },
    # Súmula 14 do TST: metade do aviso, do 13º e das férias proporcionais.
    "culpa_reciproca": {
        "mtv": "05",
        "aviso": 0.5,
        "decimo": 0.5,
        "ferias": 0.5,
        "multa": 0.20,
    },
    # Termo certo: sem aviso nem multa (Súmula 171 do TST: férias proporcionais).
    "termino_contrato": {
        "mtv": "06",
        "aviso": 0.0,
        "decimo": 1.0,
        "ferias": 1.0,
        "multa": 0.0,
    },
    # Aviso devido pelo empregado (art. 487, §2º), nunca pelo empregador.
    "pedido_demissao": {
        "mtv": "07",
        "aviso": 0.0,
        "decimo": 1.0,
        "ferias": 1.0,
        "multa": 0.0,
    },
    # Art. 483 da CLT: o empregador faltoso responde como na dispensa sem justa causa.
    "rescisao_indireta": {
        "mtv": "17",
        "aviso": 1.0,
        "decimo": 1.0,
        "ferias": 1.0,
        "multa": 0.40,
    },
    # Art. 502 da CLT e art. 18, §2º, da Lei 8.036/90: multa de 20%, sem aviso.
    "forca_maior": {
        "mtv": "27",
        "aviso": 0.0,
        "decimo": 1.0,
        "ferias": 1.0,
        "multa": 0.20,
    },
    # Art. 484-A da CLT: metade do aviso e multa de 20%.
    "acordo": {"mtv": "33", "aviso": 0.5, "decimo": 1.0, "ferias": 1.0, "multa": 0.20},
}
# Sem tipo informado (holerite antigo), vale o que o módulo sempre fez: 13º e
# férias proporcionais devidos, sem aviso nem multa.
L10N_BR_REGRA_RESCISAO_PADRAO = {
    "mtv": False,
    "aviso": 0.0,
    "decimo": 1.0,
    "ferias": 1.0,
    "multa": 0.0,
}
# Tipos que dão direito a aviso prévio indenizado pago pelo empregador.
L10N_BR_TIPOS_RESCISAO_COM_AVISO_E_MULTA = tuple(
    tipo for tipo, regra in L10N_BR_REGRAS_RESCISAO.items() if regra["aviso"]
)


class HrPayslip(models.Model):
    _inherit = "hr.payslip"

    l10n_br_abono_pecuniario = fields.Boolean(
        string="Abono Pecuniário",
        help="Venda de 1/3 dos dias de férias (CLT art. 143). Caminho "
        "LEGADO, sem alocação vinculada: presume período de 30 dias de "
        "direito e vende 10. Para respeitar os dias de direito reais "
        "(CLT art. 130) e o fracionamento, vincule "
        "l10n_br_ferias_allocation_id e use l10n_br_dias_abono.",
    )
    l10n_br_ferias_allocation_id = fields.Many2one(
        comodel_name="hr.leave.allocation",
        string="Período Aquisitivo (Férias)",
        index=True,
        domain="[('employee_id', '=', employee_id)]",
        help="Alocação de férias (período aquisitivo, CLT art. 130) cujo "
        "direito está sendo pago neste holerite. Define os dias de "
        "direito (30/24/18/12/0 conforme as faltas injustificadas) e "
        "permite o fracionamento em até 3 períodos (CLT art. 134 §1º, "
        "Lei 13.467/2017): cada holerite de férias paga os dias DESTE "
        "período/fração gozado, não o saldo inteiro da alocação.",
    )
    l10n_br_dias_direito_ferias = fields.Float(
        string="Dias de Direito (Período Aquisitivo)",
        compute="_compute_dias_direito_ferias",
        help="Dias de férias a que o empregado tem direito no período "
        "aquisitivo vinculado, conforme as faltas injustificadas "
        "(CLT art. 130): 30/24/18/12/0 dias. Informativo.",
    )
    l10n_br_dias_periodo_gozado = fields.Integer(
        string="Dias Gozados neste Período",
        help="Dias corridos efetivamente GOZADOS neste holerite - uma das "
        "até 3 frações do período aquisitivo vinculado (CLT art. 134 §1º). "
        "Só tem efeito quando l10n_br_ferias_allocation_id está definido; "
        "sem alocação, usa-se o caminho legado (l10n_br_abono_pecuniario).",
    )
    l10n_br_dias_abono = fields.Integer(
        string="Dias de Abono Pecuniário (Venda)",
        help="Dias vendidos como abono pecuniário NESTE holerite (CLT art. "
        "143), até 1/3 dos dias de direito do período aquisitivo vinculado. "
        "O abono é indivisível (CLT art. 143 §2º): só pode ser lançado em "
        "UMA das frações. Só tem efeito com l10n_br_ferias_allocation_id "
        "definido; sem alocação, usa-se l10n_br_abono_pecuniario (legado).",
    )
    l10n_br_ferias_salario = fields.Float(
        string="Salário na Remuneração das Férias",
        copy=False,
        readonly=True,
        help="Salário contratual que entrou na remuneração das férias, "
        "gravado no cálculo (TG-99): o recibo mostra o que foi pago, não o "
        "que o contrato diz hoje. Zero em holerite calculado antes deste campo.",
    )
    l10n_br_ferias_media = fields.Float(
        string="Média das Variáveis na Remuneração das Férias",
        copy=False,
        readonly=True,
        help="Média das verbas variáveis habituais (RF-18) gravada no cálculo.",
    )
    l10n_br_ferias_adicionais = fields.Float(
        string="Adicionais Fixos na Remuneração das Férias",
        copy=False,
        readonly=True,
        help="Periculosidade e insalubridade (TG-88/TG-130) gravadas no cálculo.",
    )
    l10n_br_dias_ferias_gozadas = fields.Integer(
        string="Dias de Férias Gozadas",
        compute="_compute_dias_ferias_gozadas",
    )
    l10n_br_dias_ferias_dobro = fields.Integer(
        string="Dias de Férias em Dobro",
        compute="_compute_dias_ferias_dobro",
        help="Dias corridos do gozo deste recibo depois do fim do período "
        "concessivo do período aquisitivo vinculado (CLT art. 134): pagos em "
        "dobro, com o terço (CLT art. 137). Só os dias depois do concessivo "
        "dobram, quando o gozo o atravessa (Súmula 81 do TST). O abono "
        "pecuniário tem a regra própria de ``l10n_br_dias_abono_dobro``.",
    )
    l10n_br_dias_abono_dobro = fields.Integer(
        string="Dias de Abono em Dobro",
        compute="_compute_dias_ferias_dobro",
        help="Dias de abono pecuniário pagos em dobro, com o terço (TG-139#P1): "
        "todos os dias de abono do recibo quando o gozo começa depois do fim do "
        "concessivo (a data em que as férias foram concedidas); zero se o gozo "
        "começa dentro dele, ainda que o atravesse.",
    )
    l10n_br_avos_13 = fields.Integer(
        string="Avos de 13º",
        compute="_compute_avos_13",
    )
    l10n_br_avos_13_proporcional = fields.Integer(
        string="Avos de 13º Proporcional",
        compute="_compute_avos_13",
        help="Avos do 13º até a data do desligamento (regra dos 15 dias), "
        "sem a projeção do aviso prévio indenizado: base do DECIMO_RESCISAO "
        "(natureza 6002 do eSocial; campo 63 do TRCT).",
    )
    l10n_br_avos_13_aviso = fields.Integer(
        string="Avos de 13º do Aviso Indenizado",
        compute="_compute_avos_13",
        help="Avos que a projeção do aviso prévio indenizado acrescenta ao 13º "
        "(Súmula 371 TST), inclusive os do ano seguinte: base do "
        "DECIMO_AVISO_INDENIZADO (natureza 6001 do eSocial; campo 70 do TRCT).",
    )
    l10n_br_avos_ferias = fields.Integer(
        string="Avos de Férias Proporcionais",
        compute="_compute_avos_ferias",
        help="Meses (fração >= 15 dias) do período aquisitivo em curso, "
        "usados para as férias proporcionais na rescisão. Quando o aviso "
        "prévio é INDENIZADO (rescisão sem justa causa ou acordo), o "
        "contrato é projetado pelos dias de aviso para este cômputo "
        "(Súmula 371 TST).",
    )
    l10n_br_primeira_parcela_13_paga = fields.Float(
        string="1ª Parcela do 13º já paga",
        help="Valor da 1ª parcela do 13º já paga (para cálculo da 2ª parcela)",
    )
    l10n_br_liquido_13 = fields.Float(
        string="Líquido 13º",
        compute="_compute_liquido_13",
    )

    # ══════════════════════════════════════════════════════════════════
    # RESCISÃO (RF-06)
    # ══════════════════════════════════════════════════════════════════
    l10n_br_tipo_rescisao = fields.Selection(
        selection=[
            ("sem_justa_causa", "Sem Justa Causa (Iniciativa do Empregador)"),
            ("pedido_demissao", "Pedido de Demissão"),
            ("justa_causa", "Justa Causa (CLT art. 482)"),
            ("acordo", "Comum Acordo (CLT art. 484-A)"),
            ("rescisao_indireta", "Rescisão Indireta (CLT art. 483)"),
            ("culpa_reciproca", "Culpa Recíproca (CLT art. 484)"),
            ("forca_maior", "Força Maior (CLT art. 502)"),
            ("termino_contrato", "Término do Contrato a Prazo"),
            (
                "antecipado_empregador",
                "Término Antecipado pelo Empregador (CLT art. 479)",
            ),
            (
                "antecipado_empregado",
                "Término Antecipado pelo Empregado (CLT art. 480)",
            ),
        ],
        string="Tipo de Rescisão",
        help="Determina quais verbas são devidas: aviso prévio indenizado "
        "e multa do FGTS somente em 'sem justa causa' (100%/40%) e "
        "'acordo' (CLT art. 484-A, I, 'a' e 'b': 50%/20%); férias "
        "proporcionais excluídas na justa causa (Súmula 171 TST; CLT art. "
        "146 parágrafo único e art. 147); 13º proporcional excluído "
        "SOMENTE na justa causa (Lei 4.090/62 art. 3º; Decreto 57.155/65 "
        "art. 7º) - devido inclusive no pedido de demissão (Súmula 157 "
        "TST); férias vencidas devidas em qualquer hipótese (CLT art. 146, "
        "caput). Culpa recíproca (art. 484 CLT; Súmula 14 TST): metade do "
        "aviso, do 13º e das férias proporcionais e multa de 20%. Força maior "
        "(art. 502): multa de 20%, sem aviso. Rescisão indireta: como a "
        "dispensa sem justa causa. Contrato a prazo: sem aviso nem multa no "
        "término do prazo; antecipado pelo empregador, indenização do art. "
        "479 e multa de 40%; antecipado pelo empregado, indenização do art. "
        "480, sem multa.",
    )
    l10n_br_aviso_previo = fields.Selection(
        selection=[
            ("indenizado", "Indenizado"),
            ("trabalhado", "Trabalhado"),
            ("nao_aplicavel", "Não Aplicável"),
            ("nao_cumprido", "Não Cumprido pelo Empregado"),
        ],
        string="Aviso Prévio",
        help="INDENIZADO: gera a verba AVISO_PREVIO_INDENIZADO e projeta o "
        "contrato para o 13º e as férias proporcionais (Súmula 371 TST). "
        "TRABALHADO: já remunerado pela folha mensal do próprio período; "
        "esta rescisão não gera verba adicional (date_to já reflete o fim "
        "do aviso trabalhado). NÃO APLICÁVEL: justa causa ou pedido de "
        "demissão sem aviso indenizado pelo empregador. NÃO CUMPRIDO: o "
        "empregado que pediu demissão não cumpriu o aviso e o empregador "
        "desconta 30 dias de salário (CLT art. 487, §2º).",
    )
    l10n_br_data_termo_contrato = fields.Date(
        string="Termo do Contrato a Prazo",
        help="Data final pactuada do contrato de experiência ou por prazo "
        "determinado. Base da indenização do término antecipado: metade da "
        "remuneração dos dias que faltavam até esta data (CLT art. 479, "
        "pelo empregador; art. 480, pelo empregado).",
    )
    l10n_br_prejuizo_art_480 = fields.Float(
        string="Prejuízo do Empregador (art. 480)",
        help="Prejuízo comprovado do empregador com o término antecipado pelo "
        "empregado. O desconto é este valor, limitado ao que o empregado "
        "receberia pelo art. 479 (CLT art. 480, §1º) e a um mês de "
        "remuneração (CLT art. 477, §5º). Em branco, não há desconto.",
    )
    l10n_br_fgts_saldo_conta = fields.Float(
        string="Saldo FGTS na Conta Vinculada",
        help="Base da multa de 40% (ou 20% no acordo) do FGTS (Lei "
        "8.036/90 art. 18 §1º; CLT art. 484-A, I, 'b'): "
        "total depositado na conta vinculada durante o contrato, conforme "
        "o extrato oficial (FGTS Digital), posicionado ANTES do mês da "
        "rescisão: a regra soma o depósito do mês da rescisão e o do mês "
        "anterior (vence no dia 20 do mês da rescisão), os recibos de férias "
        "cuja competência, a que este sistema declara no S-1200 (o recibo inteiro "
        "no mês em que o gozo começa), é a do mês "
        "anterior ou a da rescisão e o FGTS do 13º pago em um desses dois meses "
        "(em janeiro, o de dezembro do ano anterior); o que já venceu antes "
        "está no extrato e não soma de novo. Extrato posicionado depois do dia "
        "20 do mês da rescisão já traz o mês anterior: a base o soma de novo. "
        "Não aceita valor "
        "negativo. Zero e em branco são a mesma coisa: a "
        "regra usa o FALLBACK 8% x salário x meses trabalhados - uma "
        "ESTIMATIVA sem juros/correção monetária, que subestima o saldo "
        "real; preencher com o extrato sempre que disponível.",
    )

    l10n_br_aviso_regras = fields.Text(
        string="Aviso das Regras Personalizadas",
        compute="_compute_l10n_br_aviso_regras",
        help="Regras da rescisão personalizadas que ficaram defasadas em "
        "relação às deste módulo (TG-138): o líquido ou a multa do FGTS "
        "podem estar errados até a regra ser ajustada.",
    )

    @api.constrains("l10n_br_primeira_parcela_13_paga")
    def _check_l10n_br_primeira_parcela_13_paga(self):
        for rec in self:
            if rec.l10n_br_primeira_parcela_13_paga < 0:
                raise ValidationError(
                    _("A 1ª parcela do 13º já paga não pode ser negativa.")
                )

    @api.constrains(
        "l10n_br_tipo_rescisao",
        "l10n_br_aviso_previo",
        "l10n_br_data_termo_contrato",
        "l10n_br_prejuizo_art_480",
        "date_to",
    )
    def _check_l10n_br_rescisao_prazo(self):
        for rec in self:
            tipo = rec.l10n_br_tipo_rescisao
            if rec.l10n_br_aviso_previo == "nao_cumprido" and (
                tipo != "pedido_demissao"
            ):
                raise ValidationError(
                    _(
                        "O aviso prévio 'Não Cumprido pelo Empregado' só vale "
                        "no pedido de demissão (CLT art. 487, §2º)."
                    )
                )
            if rec.l10n_br_prejuizo_art_480 < 0:
                raise ValidationError(
                    _("O prejuízo do art. 480 não pode ser negativo.")
                )
            if tipo in ("antecipado_empregador", "antecipado_empregado"):
                if not rec.l10n_br_data_termo_contrato:
                    raise ValidationError(
                        _(
                            "Informe o Termo do Contrato a Prazo: a "
                            "indenização do término antecipado (CLT arts. 479 "
                            "e 480) depende dos dias que faltavam."
                        )
                    )
                if rec.date_to and rec.l10n_br_data_termo_contrato <= rec.date_to:
                    raise ValidationError(
                        _(
                            "O termo do contrato (%(termo)s) deve ser posterior "
                            "ao desligamento (%(deslig)s) no término antecipado."
                        )
                        % {
                            "termo": rec.l10n_br_data_termo_contrato,
                            "deslig": rec.date_to,
                        }
                    )

    @api.constrains("l10n_br_fgts_saldo_conta")
    def _check_l10n_br_fgts_saldo_conta(self):
        for rec in self:
            if rec.l10n_br_fgts_saldo_conta < 0:
                raise ValidationError(
                    _("O saldo do FGTS na conta vinculada não pode ser negativo.")
                )

    @api.depends("l10n_br_ferias_allocation_id.number_of_days")
    def _compute_dias_direito_ferias(self):
        for rec in self:
            rec.l10n_br_dias_direito_ferias = (
                rec.l10n_br_ferias_allocation_id.number_of_days
                if rec.l10n_br_ferias_allocation_id
                else 0.0
            )

    # ------------------------------------------------------------------
    # Integridade entre holerites dependentes (TG-82 e TG-83)
    #
    # Três holerites do mesmo contrato e período dependem uns dos outros:
    #
    # * o RECIBO DE FÉRIAS define os dias gozados (que saem do salário do mês
    #   e do saldo da rescisão), a base e o INSS retido (apurado na competência
    #   do mensal);
    # * o MENSAL paga o salário dos dias fora das férias;
    # * a RESCISÃO desconta o que o mensal já pagou (SALDO_SALARIO).
    #
    # A "participação" de um holerite é o que ele entrega aos dependentes: do
    # mensal, o total do salário (SALARIO_BASE e SALARIO_MATERNIDADE) e dos
    # adicionais fixos (periculosidade e insalubridade, TG-130) e o FGTS (base
    # da multa da rescisão, TG-92); do recibo,
    # o gozo (dias e fim), a base e o INSS retido; 0 se cancelado ou de outra
    # estrutura. UM ÚNICO gancho
    # (write/create/unlink, a exclusão de linhas e o compute_sheet) compara a
    # participação antes e depois de QUALQUER gravação (estado, linhas,
    # período, contrato, estrutura, dias): se mudou, os dependentes em
    # rascunho/verificação são recalculados na mesma transação e a gravação é
    # recusada se algum estiver confirmado (volte-o para rascunho antes).
    # Nada é guardado entre chamadas: o "antes" é variável local, então um
    # rollback não deixa participação velha para trás.
    # ------------------------------------------------------------------
    _L10N_BR_CAMPOS_PARTICIPACAO = (
        "state",
        "l10n_br_estorno",
        "refunded_id",
        "line_ids",
        "date_from",
        "date_to",
        "contract_id",
        "struct_id",
        "l10n_br_ferias_allocation_id",
        "l10n_br_dias_periodo_gozado",
        "l10n_br_abono_pecuniario",
    )
    _L10N_BR_PARTICIPACAO_NULA = (0, False, False, 0.0, None)
    # Estruturas que pagam o 13º inteiro do ano (a 2ª parcela já abate a 1ª).
    _L10N_BR_ESTRUTURAS_13_COMPLETO = ("13_2PARCELA", "13_SALARIO")
    # NET que soma a multa: direto (MULTA_FGTS) ou pela categoria COMP, em
    # qualquer grafia: categories.COMP, categories["COMP"], categories.get("COMP").
    _L10N_BR_NET_SOMA_MULTA = re.compile(
        r"\bMULTA_FGTS\b"
        r"|\bcategories\s*(?:\.\s*COMP\b|\[\s*[\"']COMP[\"']\s*\]"
        r"|\.\s*get\(\s*[\"']COMP[\"'])"
    )

    def _l10n_br_participacao(self):
        """{id: (contrato, de, até, valor, tipo)}; valor 0 fora da integridade."""
        res = {}
        for slip in self:
            valor, tipo = 0.0, None
            if slip.state != "cancel" and not slip.l10n_br_fora_de_vigor:
                if slip._l10n_br_eh_mensal():
                    tipo = "mensal"
                    salario = sum(
                        ln.total
                        for ln in slip.line_ids
                        if ln.code
                        in self._L10N_BR_CODIGOS_SALARIO_MENSAL
                        + self._L10N_BR_CODIGOS_ADICIONAIS_FIXOS
                    )
                    # O FGTS do mensal entra na base da multa da rescisão (TG-92).
                    fgts = sum(ln.total for ln in slip.line_ids if ln.code == "FGTS")
                    valor = (salario, fgts) if salario or fgts else 0.0
                elif slip.struct_id.code == "13_1PARCELA":
                    # O FGTS da 1ª parcela é abatido da rescisão do mesmo ano
                    # e entra na base da multa (TG-93); o valor da parcela é
                    # descontado do líquido da rescisão (TG-97).
                    tipo = "decimo1"
                    linhas = {ln.code: ln.total for ln in slip.line_ids}
                    pago = (linhas.get("ADIANTAMENTO_13", 0.0), linhas.get("FGTS", 0.0))
                    # Só o confirmado conta como pago para a rescisão.
                    valor = pago if any(pago) and slip.state == "done" else 0.0
                elif slip.struct_id.code in self._L10N_BR_ESTRUTURAS_13_COMPLETO:
                    # 2ª parcela (ou 13º integral): quita o 13º do ano, com o
                    # INSS, o IRRF e a pensão já retidos (TG-97).
                    tipo = "decimo1"
                    linhas = {ln.code: ln.total for ln in slip.line_ids}
                    pago = tuple(
                        linhas.get(codigo, 0.0)
                        for codigo in (
                            "DECIMO_TERCEIRO_BRUTO",
                            "INSS_13",
                            "IRRF_13",
                            "PENSAO_ALIMENTICIA_13",
                            "FGTS",
                        )
                    )
                    valor = pago if any(pago) and slip.state == "done" else 0.0
                elif slip.struct_id.code == "FERIAS":
                    tipo = "ferias"
                    linhas = {ln.code: ln.total for ln in slip.line_ids}
                    valor = (
                        slip.l10n_br_dias_ferias_gozadas,
                        linhas.get("GROSS", 0.0),
                        linhas.get("INSS", 0.0),
                        linhas.get("FGTS", 0.0),
                    )
            res[slip.id] = (
                slip.contract_id.id,
                slip.date_from,
                slip.date_to,
                valor,
                tipo,
            )
        return res

    def _l10n_br_reconciliar_participacao(self, antes, depois):
        periodos = {"mensal": set(), "ferias": set(), "decimo1": set()}
        for slip_id, chave in antes.items():
            nova = depois.get(slip_id, self._L10N_BR_PARTICIPACAO_NULA)
            if nova == chave:
                continue
            for contrato, de, ate, valor, tipo in (chave, nova):
                if valor and contrato:
                    periodos[tipo].add((contrato, de, ate))
        if not any(periodos.values()):
            return
        mensais = self.browse()
        rescisoes = self.browse()
        for tipo, conjunto in periodos.items():
            for contrato, de, ate in conjunto:
                if tipo == "decimo1":
                    # Rescisões do mesmo ano da 1ª parcela, em qualquer mês.
                    rescisoes |= self.search(
                        [
                            ("contract_id", "=", contrato),
                            ("state", "!=", "cancel"),
                            ("l10n_br_fora_de_vigor", "=", False),
                            ("struct_id.code", "=", "RESCISAO"),
                            ("date_to", ">=", date(ate.year, 1, 1)),
                            ("date_to", "<=", date(ate.year, 12, 31)),
                        ]
                    )
                    continue
                dominio = [
                    ("contract_id", "=", contrato),
                    ("state", "!=", "cancel"),
                    ("l10n_br_fora_de_vigor", "=", False),
                    ("date_from", "<=", ate),
                    ("date_to", ">=", de),
                ]
                rescisoes |= self.search(
                    dominio + [("struct_id.code", "=", "RESCISAO")]
                )
                if tipo == "ferias":
                    mensais |= self.search(
                        dominio
                        + [("struct_id", "in", self._l10n_br_estruturas_mensais().ids)]
                    )
        # Quem entra na base da multa de uma rescisão (TG-138 r2): o MESMO
        # predicado da soma, não um filtro paralelo.
        candidatas = {}
        for tipo, conjunto in periodos.items():
            for contrato, de, ate in conjunto:
                if contrato not in candidatas:
                    candidatas[contrato] = self.search(
                        [
                            ("contract_id", "=", contrato),
                            ("state", "!=", "cancel"),
                            ("l10n_br_fora_de_vigor", "=", False),
                            ("struct_id.code", "=", "RESCISAO"),
                        ]
                    )
                rescisoes |= candidatas[contrato].filtered(
                    lambda r, t=tipo, d=de, a=ate: r._l10n_br_entra_na_base_multa(
                        t, d, a
                    )
                )
        dependentes = (mensais | rescisoes) - self
        fechados = dependentes.filtered(lambda r: r.state not in ("draft", "verify"))
        if fechados:
            raise UserError(
                _(
                    "Não é possível alterar este holerite: %(fechados)s, do mesmo "
                    "contrato e período, já está confirmado e depende dele (dias "
                    "de férias, salário, FGTS do mês e do 13º ou saldo compensado). "
                    "Volte o confirmado "
                    "para rascunho primeiro.",
                    fechados=", ".join(fechados.mapped(lambda r: r.number or r.name)),
                )
            )
        # Os mensais primeiro: o recálculo de cada um já reconcilia a rescisão
        # se o salário pago mudou; a rescisão é recalculada ao fim por causa
        # dos dias de férias, que ela também desconta.
        (mensais - self).compute_sheet()
        (rescisoes - self).compute_sheet()

    @api.model_create_multi
    def create(self, vals_list):
        slips = super().create(vals_list)
        slips._l10n_br_reconciliar_participacao(
            {i: self._L10N_BR_PARTICIPACAO_NULA for i in slips.ids},
            slips._l10n_br_participacao(),
        )
        slips._l10n_br_atualizar_notas_ausencias()
        return slips

    def _l10n_br_atualizar_notas_ausencias(self):
        """O recibo de férias fixa o período que a ausência debita: ao lançar,
        alterar ou cancelar o recibo, os avisos e notas das ausências do empregado
        são reconferidos (TG-139)."""
        ferias = self.filtered(lambda slip: slip.struct_id.code == "FERIAS")
        if ferias:
            self.env["hr.leave"]._l10n_br_atualizar_notas(ferias.employee_id)

    def _l10n_br_posto_na_confirmacao(self):
        """0 férias/13º, 1 mensal, 2 rescisão: quem depende de quem (TG-138)."""
        self.ensure_one()
        if self.struct_id.code == "RESCISAO":
            return 2
        return 1 if self._l10n_br_eh_mensal() else 0

    def write(self, vals):
        if vals.get("state") == "done" and len(self) > 1:
            # Confirmar em lote: quem depende do outro só é gravado depois, para
            # ser recalculado com o que o outro pagou (a rescisão no mesmo
            # lote da 1ª parcela ou do mensal não pode fechar com valor velho).
            postos = {slip.id: slip._l10n_br_posto_na_confirmacao() for slip in self}
            if len(set(postos.values())) > 1:
                res = True
                for posto in sorted(set(postos.values())):
                    res = self.filtered(lambda s, p=posto: postos[s.id] == p).write(
                        vals
                    )
                return res
        if (
            not self
            or self.env.context.get("l10n_br_em_compute")
            or not set(vals) & set(self._L10N_BR_CAMPOS_PARTICIPACAO)
        ):
            res = super().write(vals)
        else:
            antes = self._l10n_br_participacao()
            res = super().write(vals)
            self._l10n_br_reconciliar_participacao(antes, self._l10n_br_participacao())
        if {
            "state",
            "l10n_br_ferias_allocation_id",
            "date_from",
            "struct_id",
        } & set(vals):
            self._l10n_br_atualizar_notas_ausencias()
        return res

    def unlink(self):
        antes = self._l10n_br_participacao()
        employees = self.filtered(
            lambda slip: slip.struct_id.code == "FERIAS"
        ).employee_id
        res = super().unlink()
        self.browse()._l10n_br_reconciliar_participacao(antes, {})
        self.env["hr.leave"]._l10n_br_atualizar_notas(employees)
        return res

    @staticmethod
    def _l10n_br_codigo_da_formula(formula):
        """Fórmula sem os comentários (para procurar o que ela de fato usa)."""
        return "\n".join(
            linha.split("#", 1)[0] for linha in (formula or "").splitlines()
        )

    def _l10n_br_avisos_regras(self):
        """Avisos sobre regras da rescisão personalizadas e defasadas (TG-138).

        As regras são ``noupdate``: o cliente que as personalizou não recebe as
        fórmulas novas. O módulo não mexe na fórmula dele, mas o gestor precisa
        ver quando ela diverge: a multa do FGTS é informativa, fora do NET.
        """
        self.ensure_one()
        if self.struct_id.code != "RESCISAO":
            return []
        regras = {r.code: r for r in self.struct_id.rule_ids}
        codigo = {
            c: self._l10n_br_codigo_da_formula(r.amount_python_compute)
            for c, r in regras.items()
        }
        avisos = []
        if re.search(self._L10N_BR_NET_SOMA_MULTA, codigo.get("NET", "")):
            avisos.append(
                _(
                    "A regra NET (Líquido da Rescisão) está personalizada e soma "
                    "a multa do FGTS. A multa vai à conta vinculada pela guia do "
                    "FGTS Digital, não ao líquido do TRCT: o líquido está maior "
                    "que o devido. Retire MULTA_FGTS da regra NET."
                )
            )
        multa = codigo.get("MULTA_FGTS", "")
        if (
            multa
            and "_l10n_br_fgts_13_primeira_depositado" in codigo.get("FGTS_13", "")
            and "_l10n_br_fgts_13_" not in multa
        ):
            avisos.append(
                _(
                    "A regra MULTA_FGTS está personalizada e não soma o FGTS das "
                    "parcelas do 13º já pagas, que o FGTS_13 desta rescisão "
                    "abate: a base da multa está menor que a devida. Some "
                    "payslip._l10n_br_fgts_13_na_base_multa(contract) aos "
                    "depósitos."
                )
            )
        return avisos

    def _compute_l10n_br_aviso_regras(self):
        for slip in self:
            slip.l10n_br_aviso_regras = "\n".join(slip._l10n_br_avisos_regras())

    def _l10n_br_postar_avisos_regras(self):
        """Nota no registro (uma vez por aviso): o log do migrador não chega ao gestor."""
        for slip in self:
            avisos = slip._l10n_br_avisos_regras()
            if not avisos:
                continue
            anteriores = " ".join(slip.message_ids.mapped("body") or [])
            for aviso in avisos:
                if html_escape(aviso) not in anteriores:
                    slip.message_post(body=html_escape(aviso))

    def _l10n_br_exigir_alocacao_periodo_completo(self):
        """TG-147: a rescisão só calcula com a alocação de Férias do último
        período aquisitivo que se completa até a data projetada.

        A alocação do ``hr_holidays`` é a única fonte do período vencido (CLT
        art. 146) e do que se completa na projeção do aviso indenizado (Súmula
        371 TST). Sem ela as férias vencidas saíam zero, sem aviso, e os dias
        proporcionais pagavam o período novo a menos. Só o período mais recente
        é exigido: os anteriores podem ter sido gozados sem alocação no legado.
        """
        vacation_type = self.env.ref(
            "l10n_br_hr_vacation.leave_type_ferias", raise_if_not_found=False
        )
        recusas = []
        for slip in self.filtered(lambda s: s.struct_id.code == "RESCISAO"):
            admissao = slip.contract_id.date_start
            if not (vacation_type and admissao and slip.date_to):
                continue
            referencia = slip._l10n_br_data_projetada_rescisao()
            anos = relativedelta(referencia + timedelta(days=1), admissao).years
            if anos < 1:
                continue
            inicio = admissao + relativedelta(years=anos - 1)
            fim = admissao + relativedelta(years=anos) - relativedelta(days=1)
            # Art. 133 § 2º: o período reiniciado no retorno ao serviço, ou
            # deslocado por afastamento, termina depois (ou antes) do
            # aniversário: vale qualquer alocação cujo fim caia entre o início
            # do período devido e a data projetada (a do período anterior
            # termina antes do início).
            if (
                self.env["hr.leave.allocation"]
                .sudo()
                .search_count(
                    [
                        ("employee_id", "=", slip.employee_id.id),
                        ("holiday_status_id", "=", vacation_type.id),
                        ("state", "=", "validate"),
                        ("date_to", ">=", inicio),
                        ("date_to", "<=", referencia),
                    ]
                )
            ):
                continue
            projetado = fim > slip.date_to
            recusas.append(
                _(
                    "Rescisão %(holerite)s de %(empregado)s: falta a alocação de "
                    "Férias validada do período aquisitivo de %(inicio)s a "
                    "%(fim)s, que se completa %(quando)s: sem ela as férias do "
                    "período (e o terço) não são pagas. Crie a alocação de "
                    "Férias do empregado com essas datas, valide-a e calcule a "
                    "rescisão de novo.",
                    holerite=slip.number or slip.name or slip.display_name,
                    empregado=slip.employee_id.name,
                    inicio=inicio.strftime("%d/%m/%Y"),
                    fim=fim.strftime("%d/%m/%Y"),
                    quando=_("na projeção do aviso prévio indenizado (até %s)")
                    % referencia.strftime("%d/%m/%Y")
                    if projetado
                    else _("antes do desligamento"),
                )
            )
        if recusas:
            raise UserError("\n".join(recusas))

    def compute_sheet(self):
        confirmados = self.filtered(lambda slip: slip.state == "done")
        if confirmados:
            raise UserError(
                _(
                    "Não é possível recalcular holerite confirmado: %(nomes)s. "
                    "Recalcular o devolveria à verificação com valores que podem "
                    "ser outros, já usados em quem depende dele. Volte-o para "
                    "rascunho primeiro.",
                    nomes=", ".join(confirmados.mapped(lambda r: r.number or r.name)),
                )
            )
        self._l10n_br_exigir_alocacao_periodo_completo()
        # O compute_sheet apaga as linhas e grava as novas: a conferência é uma
        # só, no fim, contra a participação de antes (variável local).
        antes = self._l10n_br_participacao()
        res = super(
            HrPayslip, self.with_context(l10n_br_em_compute=True)
        ).compute_sheet()
        self._l10n_br_gravar_remuneracao_ferias()
        self._l10n_br_reconciliar_participacao(antes, self._l10n_br_participacao())
        self._l10n_br_postar_avisos_regras()
        return res

    def _l10n_br_gravar_remuneracao_ferias(self):
        """Grava os componentes da remuneração das férias usados no cálculo.

        São os mesmos termos da regra ``FERIAS`` (salário, média e adicionais
        fixos). O recibo os lê daqui: recalculá-los na impressão muda o quadro
        quando o mensal é confirmado depois, o contrato é reajustado ou ganha
        periculosidade, e as linhas pagas não mudam.
        """
        for slip in self.filtered(lambda s: s.struct_id.code == "FERIAS"):
            contrato = slip.contract_id
            slip.with_context(l10n_br_em_compute=True).write(
                {
                    "l10n_br_ferias_salario": contrato.wage,
                    "l10n_br_ferias_media": slip._l10n_br_media_habitual(
                        slip._l10n_br_codes_media_habitual()
                    ),
                    "l10n_br_ferias_adicionais": slip._l10n_br_adicionais_fixos(
                        contrato, "ferias"
                    ),
                }
            )

    def _l10n_br_ferias_gozadas(self, contract):
        """Períodos de gozo dos recibos de férias que se sobrepõem a este holerite.

        A folha mensal paga só os dias fora das férias (CLT art. 129 e 145): os
        dias gozados já foram pagos no recibo de férias; vale também para a rescisão
        (SALDO_SALARIO). O período de gozo
        começa em ``date_from`` do recibo e dura ``l10n_br_dias_ferias_gozadas``
        dias (limitado a ``date_to``); os dias de abono pecuniário não entram.
        Recibos cancelados e o próprio holerite ficam de fora.
        """
        periodos = super()._l10n_br_ferias_gozadas(contract)
        self.ensure_one()
        if not self.date_from or not self.date_to or not contract:
            return periodos
        if not self._l10n_br_eh_mensal() and self.struct_id.code != "RESCISAO":
            return periodos
        recibos = self.env["hr.payslip"].search(
            [
                ("contract_id", "=", contract.id),
                ("id", "!=", self.id),
                ("state", "!=", "cancel"),
                ("l10n_br_fora_de_vigor", "=", False),
                ("struct_id.code", "=", "FERIAS"),
                ("date_from", "<=", self.date_to),
                ("date_to", ">=", self.date_from),
            ]
        )
        for recibo in recibos:
            fim = min(
                recibo.date_to,
                recibo.date_from
                + timedelta(days=max(recibo.l10n_br_dias_ferias_gozadas, 1) - 1),
            )
            periodos.append((recibo.date_from, fim))
        return periodos

    def _l10n_br_inss_ferias_competencia(self, contract):
        """INSS das férias na competência: base e valor já retido no recibo.

        O salário de contribuição do mês soma o mensal e as férias gozadas
        (Lei 8.212/91, art. 28), sob um só teto: o INSS do mensal é a alíquota
        progressiva sobre a soma, menos o que o recibo de férias já reteve.
        Entram os recibos que começam dentro do período deste mensal.
        """
        base, retido = super()._l10n_br_inss_ferias_competencia(contract)
        self.ensure_one()
        if not self.date_from or not self.date_to or not contract:
            return base, retido
        if not self._l10n_br_eh_mensal():
            return base, retido
        recibos = self.env["hr.payslip"].search(
            [
                ("contract_id", "=", contract.id),
                ("id", "!=", self.id),
                ("state", "!=", "cancel"),
                ("l10n_br_fora_de_vigor", "=", False),
                ("struct_id.code", "=", "FERIAS"),
                ("date_from", ">=", self.date_from),
                ("date_from", "<=", self.date_to),
            ]
        )
        for recibo in recibos:
            linhas = {ln.code: ln.total for ln in recibo.line_ids}
            base += linhas.get("GROSS", 0.0)
            retido += linhas.get("INSS", 0.0)
        return base, retido

    @api.depends(
        "l10n_br_ferias_allocation_id",
        "l10n_br_dias_periodo_gozado",
        "l10n_br_abono_pecuniario",
    )
    def _compute_dias_ferias_gozadas(self):
        for rec in self:
            if rec.l10n_br_ferias_allocation_id:
                # RF-19: dias GOZADOS nesta fração do período aquisitivo
                # (fracionamento em até 3 períodos, CLT art. 134 §1º).
                rec.l10n_br_dias_ferias_gozadas = rec.l10n_br_dias_periodo_gozado
            elif rec.l10n_br_abono_pecuniario:
                # Caminho LEGADO (sem alocação): 30 dias de direito
                # presumidos, vende 10 (1/3), goza 20.
                rec.l10n_br_dias_ferias_gozadas = 20
            else:
                rec.l10n_br_dias_ferias_gozadas = 30

    @api.depends(
        "l10n_br_ferias_allocation_id",
        "l10n_br_ferias_allocation_id.date_to",
        "l10n_br_dias_ferias_gozadas",
        "l10n_br_dias_abono",
        "date_from",
    )
    def _compute_dias_ferias_dobro(self):
        for rec in self:
            alloc = rec.l10n_br_ferias_allocation_id
            dias = rec.l10n_br_dias_ferias_gozadas
            rec.l10n_br_dias_ferias_dobro = 0
            rec.l10n_br_dias_abono_dobro = 0
            if (
                alloc
                and alloc.date_to
                and rec.date_from
                and rec.struct_id.code == "FERIAS"
                and rec.date_from > alloc._l10n_br_fim_concessivo()
            ):
                rec.l10n_br_dias_abono_dobro = rec.l10n_br_dias_abono
            if not alloc or not alloc.date_to or not rec.date_from or dias <= 0:
                continue
            if rec.struct_id.code != "FERIAS":
                continue
            fim_gozo = rec.date_from + timedelta(days=dias - 1)
            depois = max(
                rec.date_from, alloc._l10n_br_fim_concessivo() + timedelta(days=1)
            )
            rec.l10n_br_dias_ferias_dobro = max((fim_gozo - depois).days + 1, 0)

    @api.depends(
        "l10n_br_ferias_allocation_id",
        "l10n_br_dias_abono",
        "l10n_br_abono_pecuniario",
        "l10n_br_dias_ferias_gozadas",
    )
    def _compute_dias_ferias_vendidas(self):
        for rec in self:
            if rec.l10n_br_ferias_allocation_id:
                rec.l10n_br_dias_ferias_vendidas = rec.l10n_br_dias_abono
            elif rec.l10n_br_abono_pecuniario:
                rec.l10n_br_dias_ferias_vendidas = 30 - rec.l10n_br_dias_ferias_gozadas
            else:
                rec.l10n_br_dias_ferias_vendidas = 0

    l10n_br_dias_ferias_vendidas = fields.Integer(
        string="Dias de Férias Vendidas",
        compute="_compute_dias_ferias_vendidas",
        help="Dias vendidos como abono pecuniário neste holerite (soma o "
        "caminho novo, com alocação, e o legado, sem alocação).",
    )

    @api.constrains("l10n_br_ferias_allocation_id", "date_from", "struct_id")
    def _check_l10n_br_periodo_do_recibo(self):
        """O período do recibo de férias segue a regra da ausência (TG-139): o
        aquisitivo completo no início do gozo (CLT art. 134) e dentro do horizonte
        de cinco anos depois do concessivo (prescrição, CLT art. 149)."""
        for rec in self.filtered(lambda s: s.struct_id.code == "FERIAS"):
            alloc = rec.l10n_br_ferias_allocation_id
            if not alloc or not alloc.date_to or not rec.date_from:
                continue
            if alloc.date_to >= rec.date_from:
                raise ValidationError(
                    _(
                        "O período aquisitivo de %(inicio)s a %(fim)s ainda não "
                        "estava completo no início do gozo (%(gozo)s): férias só "
                        "se gozam depois de completo o período aquisitivo (CLT art. "
                        "134). Escolha um período já completo.",
                        inicio=fields.Date.to_string(alloc.date_from),
                        fim=fields.Date.to_string(alloc.date_to),
                        gozo=fields.Date.to_string(rec.date_from),
                    )
                )
            if alloc._l10n_br_horizonte() < rec.date_from:
                raise ValidationError(
                    _(
                        "O período aquisitivo %(inicio)s a %(fim)s está prescrito "
                        "(CLT art. 149): o sistema não lança férias desse período. "
                        "Concessão por liberalidade deve ser tratada com o "
                        "jurídico.",
                        inicio=fields.Date.to_string(alloc.date_from),
                        fim=fields.Date.to_string(alloc.date_to),
                    )
                )

    @api.constrains(
        "l10n_br_ferias_allocation_id",
        "l10n_br_dias_periodo_gozado",
        "l10n_br_dias_abono",
    )
    def _check_fracionamento_ferias(self):
        """Valida direito, indivisibilidade do abono e fracionamento (RF-19).

        CLT art. 130: dias gozados + vendidos não pode superar o direito do
        período aquisitivo. CLT art. 143 §2º: o abono é indivisível - só uma
        fração pode vendê-lo, e o limite é 1/3 do direito (não fixo em 10
        dias). CLT art. 134 §1º (Lei 13.467/2017): até 3 períodos por
        período aquisitivo, um deles com pelo menos 14 dias corridos e os
        demais com pelo menos 5 dias corridos cada.
        """
        for rec in self:
            alloc = rec.l10n_br_ferias_allocation_id
            if not alloc:
                continue
            direito = alloc.number_of_days
            if rec.l10n_br_dias_abono > direito / 3:
                raise ValidationError(
                    _(
                        "O abono pecuniário não pode superar 1/3 dos dias de "
                        "direito do período aquisitivo (CLT art. 143): "
                        "máximo de %(maximo)s dias para %(direito)s dias de "
                        "direito."
                    )
                    % {"maximo": direito / 3, "direito": direito}
                )
            if rec.l10n_br_dias_periodo_gozado < 0 or rec.l10n_br_dias_abono < 0:
                raise ValidationError(
                    _("Os dias gozados e vendidos não podem ser negativos.")
                )
            # Irmãos: demais holerites de férias (não cancelados) da MESMA
            # alocação, formando as frações do período aquisitivo.
            irmaos = self.env["hr.payslip"].search(
                [
                    ("l10n_br_ferias_allocation_id", "=", alloc.id),
                    ("state", "!=", "cancel"),
                    ("l10n_br_fora_de_vigor", "=", False),
                ]
            )
            fracoes = irmaos.filtered(lambda p: p.l10n_br_dias_periodo_gozado > 0)
            dias_fracoes = fracoes.mapped("l10n_br_dias_periodo_gozado")
            if len(fracoes) > 3:
                raise ValidationError(
                    _(
                        "As férias só podem ser fracionadas em até 3 "
                        "períodos por período aquisitivo (CLT art. 134 §1º, "
                        "Lei 13.467/2017)."
                    )
                )
            if len(fracoes) >= 2:
                if max(dias_fracoes) < 14:
                    raise ValidationError(
                        _(
                            "No fracionamento das férias, pelo menos um "
                            "período deve ter 14 dias corridos ou mais "
                            "(CLT art. 134 §1º)."
                        )
                    )
                if any(d < 5 for d in dias_fracoes):
                    raise ValidationError(
                        _(
                            "No fracionamento das férias, nenhum período "
                            "pode ter menos de 5 dias corridos "
                            "(CLT art. 134 §1º)."
                        )
                    )
            total_abono = sum(irmaos.mapped("l10n_br_dias_abono"))
            total_gozado = sum(dias_fracoes)
            if total_gozado + total_abono > direito:
                raise ValidationError(
                    _(
                        "A soma dos dias gozados e vendidos em todas as "
                        "frações deste período aquisitivo (%(total)s) supera "
                        "os %(direito)s dias de direito."
                    )
                    % {"total": total_gozado + total_abono, "direito": direito}
                )

    @api.depends(
        "contract_id", "date_to", "l10n_br_tipo_rescisao", "l10n_br_aviso_previo"
    )
    def _compute_avos_13(self):
        from odoo.addons.l10n_br_hr_payroll.models.salary_rules_br import (
            calc_decimo_avos,
        )

        for rec in self:
            if rec.contract_id and rec.date_to:
                referencia = rec._l10n_br_data_projetada_rescisao()
                admissao = rec.contract_id.date_start
                # Cada ano-base tem o seu 13º (Lei 4.090/62): o ano do
                # desligamento vai até 31/12 e o ano projetado pelo aviso
                # (Súmula 371 TST) conta de 1º/01 até a data projetada. Medir
                # só o ano da referência zerava o 13º quando o aviso cruzava
                # o ano e caía em menos de 15 dias de janeiro.
                avos = 0
                for ano in range(rec.date_to.year, referencia.year):
                    avos += calc_decimo_avos(admissao, date(ano, 12, 31))
                avos += calc_decimo_avos(admissao, referencia)
                rec.l10n_br_avos_13 = avos
                # O 13º proporcional é o do desligamento (até 12 avos); o que
                # o aviso projeta é rubrica própria (TG-136).
                proporcional = calc_decimo_avos(admissao, rec.date_to)
                rec.l10n_br_avos_13_proporcional = min(proporcional, avos)
                rec.l10n_br_avos_13_aviso = avos - rec.l10n_br_avos_13_proporcional
            else:
                rec.l10n_br_avos_13 = 0
                rec.l10n_br_avos_13_proporcional = 0
                rec.l10n_br_avos_13_aviso = 0

    @api.depends(
        "contract_id", "date_to", "l10n_br_tipo_rescisao", "l10n_br_aviso_previo"
    )
    def _compute_avos_ferias(self):
        for rec in self:
            if rec.contract_id and rec.contract_id.date_start and rec.date_to:
                referencia = rec._l10n_br_data_projetada_rescisao()
                rec.l10n_br_avos_ferias = self._calc_avos_ferias_proporcionais(
                    rec.contract_id.date_start, referencia
                )
            else:
                rec.l10n_br_avos_ferias = 0

    @staticmethod
    def _calc_avos_ferias_proporcionais(data_admissao, data_referencia):
        """Avos de férias proporcionais do período aquisitivo em curso.

        Conta os meses (alinhados ao aniversário de admissão) com fração
        igual ou superior a 15 dias, desde o início do período aquisitivo
        em curso (último aniversário de admissão <= referência) até a data
        de referência (rescisão, já projetada pelo aviso indenizado quando
        aplicável - ver ``_l10n_br_data_projetada_rescisao``). Máximo de 12
        avos.

        Nota: NÃO considera férias vencidas de períodos aquisitivos
        completos e não gozados - ver ``_l10n_br_ferias_vencidas_dados``.
        """
        anos = data_referencia.year - data_admissao.year
        inicio = data_admissao + relativedelta(years=anos)
        if inicio > data_referencia:
            inicio = data_admissao + relativedelta(years=anos - 1)
        avos = 0
        cursor = inicio
        while cursor <= data_referencia:
            fim_mes = cursor + relativedelta(months=1) - relativedelta(days=1)
            if fim_mes <= data_referencia:
                avos += 1
            else:
                dias = (data_referencia - cursor).days + 1
                if dias >= 15:
                    avos += 1
            cursor += relativedelta(months=1)
        return min(avos, 12)

    # ------------------------------------------------------------------
    # Periculosidade e insalubridade na base das verbas (CLT art. 142 § 6º)
    # ------------------------------------------------------------------

    def _l10n_br_janela_adicionais(self, contract, verba):
        """``(inicio, fim)`` do período de que sai a média dos adicionais.

        - ``ferias``: o período aquisitivo da alocação do recibo (sem
          alocação, os 12 meses anteriores ao recibo);
        - ``ferias_proporcionais``: o período aquisitivo em curso na rescisão,
          do último aniversário de admissão até a data (projetada) do
          desligamento;
        - ``13``: o ano civil do holerite.
        """
        self.ensure_one()
        if verba == "13":
            ano = (self.date_to or self.date_from).year
            return date(ano, 1, 1), date(ano, 12, 31)
        if verba == "ferias_proporcionais":
            referencia = self._l10n_br_data_projetada_rescisao()
            anos = referencia.year - contract.date_start.year
            inicio = contract.date_start + relativedelta(years=anos)
            if inicio > referencia:
                inicio = contract.date_start + relativedelta(years=anos - 1)
            return inicio, referencia
        alocacao = self.l10n_br_ferias_allocation_id
        if alocacao and alocacao.date_from and alocacao.date_to:
            return alocacao.date_from, alocacao.date_to
        referencia = self.date_from or self.date_to
        return referencia - relativedelta(months=12), referencia - timedelta(days=1)

    def _l10n_br_adicionais_fixos(self, contract, verba=None, periodo=None):
        """Periculosidade e insalubridade na remuneração-base de ``verba``.

        TG-133, CLT art. 142 § 6º (letra da lei, decisão TG-133#P1):

        - ``verba`` vazia ou ``momento`` (aviso prévio indenizado, art. 479 e
          480, desconto do aviso): a remuneração do momento, o valor cheio
          vigente no contrato, sem média;
        - ``ferias`` (férias, abono, férias vencidas), ``ferias_proporcionais``
          e ``13``: o valor cheio vigente SE o adicional foi uniforme em todos
          os meses do período (aquisitivo, ou ano civil no 13º); senão a média
          duodecimal do período, atualizada pelos reajustes posteriores
          (``_l10n_br_media_adicionais_art142``). Quem tem o adicional hoje
          mas não o teve no período todo leva a média, não o cheio.

        ``periodo`` troca a janela padrão (férias vencidas: o período de cada
        alocação). Sem mensais confirmados no período, vale o vigente.
        """
        self.ensure_one()
        vigente = self._l10n_br_adicionais_fixos_vigentes(contract)
        if verba not in ("ferias", "ferias_proporcionais", "13"):
            return vigente
        inicio, fim = periodo or self._l10n_br_janela_adicionais(contract, verba)
        media = self._l10n_br_media_adicionais_art142(contract, inicio, fim, vigente)
        return vigente if media is None else media

    def _l10n_br_media_adicionais_art142(self, contract, inicio, fim, vigente):
        """Média dos adicionais fixos pagos nos mensais de ``inicio`` a ``fim``.

        Devolve ``None`` quando não há mensal confirmado no período com dias
        de salário, ou quando o adicional foi uniforme (igual ao ``vigente``
        em todos os meses, já atualizado): aí vale o vigente.

        - Mensais confirmados, com competência no período e anterior a este
          holerite (como a média das demais verbas, RF-18).
        - Divisor: os dias de salário de cada mês dividido por 30. Mês sem
          dias de salário (férias gozadas o mês inteiro, afastamento) fica de
          fora; mês parcial entra proporcional aos dias trabalhados (o valor
          pago já é proporcional). Escolha da decisão TG-133#P1 (item 3); a lei
          manda a média "duodecimal" e não diz como tratar o mês sem salário.
        - Reajuste: cada importância é multiplicada por salário atual /
          salário do mês (periculosidade, sobre o salário) ou salário mínimo
          atual / salário mínimo do mês (insalubridade, sobre o mínimo). O
          salário do mês vem das rubricas de salário do holerite e dos dias
          de salário dele.
        """
        self.ensure_one()
        referencia = self.date_from or self.date_to
        if not contract or not referencia:
            return None
        mensais = self.env["hr.payslip"].search(
            [
                ("contract_id", "=", contract.id),
                ("struct_id", "in", self._l10n_br_estruturas_mensais().ids),
                ("state", "=", "done"),
                ("l10n_br_fora_de_vigor", "=", False),
                ("date_from", "<", referencia),
                ("date_from", ">=", inicio),
                ("date_from", "<=", fim),
            ],
            order="date_from",
        )
        faixa = self.env["l10n_br.hr.payroll.inss.faixa"]
        minimo_atual = faixa._salario_minimo(self._get_competencia())
        total, peso, uniforme = 0.0, 0.0, True
        for mensal in mensais:
            dias = salary_rules_br.dias_salario_mes(
                mensal.date_from,
                mensal.date_to,
                contract.date_start,
                contract.date_end,
                mensal._l10n_br_afastamentos_inss(contract),
                mensal._l10n_br_ferias_gozadas(contract),
            )
            if dias <= 0:
                continue
            totais = {}
            for linha in mensal.line_ids:
                totais[linha.code] = totais.get(linha.code, 0.0) + linha.total
            salario_pago = sum(
                totais.get(c, 0.0) for c in self._L10N_BR_CODIGOS_SALARIO_MENSAL
            )
            salario_mes = round(salario_pago * 30 / dias, 2)
            # Tolerância do arredondamento do salário proporcional do mês.
            if (
                not salario_mes
                or abs(salario_mes - contract.wage) <= 0.005 * 30 / dias + 0.005
            ):
                fator_salario = 1.0
            else:
                fator_salario = contract.wage / salario_mes
            minimo_mes = faixa._salario_minimo(mensal._get_competencia())
            fator_minimo = minimo_atual / minimo_mes if minimo_mes else 1.0
            atualizado = totais.get(
                "ADICIONAL_PERICULOSIDADE", 0.0
            ) * fator_salario + totais.get("ADICIONAL_INSALUBRIDADE", 0.0) * (
                fator_minimo
            )
            total += atualizado
            peso += dias / 30
            if abs(atualizado * 30 / dias - vigente) > 0.01 + 0.005 * 30 / dias:
                uniforme = False
        if not peso or uniforme:
            return None
        return salary_rules_br.round_money(total / peso)

    @staticmethod
    def _l10n_br_codes_media_habitual():
        """Códigos de rubrica cuja média (RF-18) compõe férias/13º/rescisão.

        Súmula 45 TST / CLT art. 142: parcelas variáveis habituais (horas
        extras habituais, adicional noturno) integram pela MÉDIA dos
        últimos meses. Adicionais CONTRATUAIS fixos (periculosidade,
        insalubridade) são um percentual constante do salário - não variam
        mês a mês - e por isso ficam FORA desta lista: entram na base das
        apurações separadas pelo valor CHEIO do contrato
        (``tools.br.adicionais_fixos``, TG-88), não por média.

        O reflexo dessas verbas no DSR (``DSR_HE``, ``DSR_NOTURNO``) integra
        a média junto com elas (Súmulas 172 e 60 do TST).
        """
        return (
            "HE_50",
            "HE_100",
            "ADICIONAL_NOTURNO",
            "DSR_HE",
            "DSR_NOTURNO",
        )

    def _l10n_br_dias_aviso_previo(self):
        """Dias de aviso prévio devidos (Lei 12.506/2011). Ver salary_rules_br.

        O acréscimo de 3 dias por ano é só a favor do empregado (Lei 12.506/2011,
        art. 1º, parágrafo único; aviso prévio que o empregador deve ao empregado):
        no pedido de demissão o prazo do aviso é de 30 dias (CLT art. 487, I).
        """
        self.ensure_one()
        if not self.contract_id or not self.contract_id.date_start or not self.date_to:
            return 0
        if self.l10n_br_tipo_rescisao == "pedido_demissao":
            return 30
        from odoo.addons.l10n_br_hr_payroll.models.salary_rules_br import (
            calc_aviso_previo_dias,
        )

        return calc_aviso_previo_dias(self.contract_id.date_start, self.date_to)

    def _l10n_br_competencia_anterior(self):
        """(início, fim) do mês anterior ao do desligamento (R-1)."""
        self.ensure_one()
        fim = self.date_to.replace(day=1) - timedelta(days=1)
        return fim.replace(day=1), fim

    def _l10n_br_janela_base_multa(self):
        """Janelas de competência da base da multa do FGTS desta rescisão (R).

        Com o saldo informado (extrato posicionado ANTES de R, que só traz o que
        venceu até o dia 20 de R: competências até R-2), a base soma as
        competências R-1 e R. Sem saldo (estimativa 8% x salário), só o mês de R
        e o 13º do ano. Devolve ``(inicio, fim, inicio_13, fim_13)``.
        """
        self.ensure_one()
        fim = (self.date_to.replace(day=28) + timedelta(days=4)).replace(
            day=1
        ) - timedelta(days=1)
        if self.l10n_br_fgts_saldo_conta:
            inicio = self._l10n_br_competencia_anterior()[0]
            return inicio, fim, inicio, fim
        ano = self.date_to.year
        return self.date_from, fim, date(ano, 1, 1), date(ano, 12, 31)

    def _l10n_br_entra_na_base_multa(self, tipo, de, ate):
        """Um holerite de ``tipo`` (mensal, ferias, decimo1) de ``de`` a ``ate`` entra na base?

        ÚNICA decisão de quais holerites compõem a base da multa (TG-138 r2):
        a soma do FGTS (``_l10n_br_holerites_da_base_multa``) e o gancho de
        integridade (quem depende de um holerite alterado) usam este predicado.

        * ``mensal``: o período se sobrepõe à janela.
        * ``ferias``: com saldo informado, pela competência que este sistema
          declara no S-1200 (``l10n_br_esocial``: recibo inteiro no mês de
          ``date_from``), dentro da janela; o recibo de 20/10 a 18/11 é de
          outubro, mesmo com R em dezembro. Sem saldo informado, como já era: o
          recibo que se sobrepõe ao período da rescisão. (O MOS 23.1 (c) rateia
          por dias de gozo em cada mês; essa divergência é tratada fora da TG-138.)
        * ``decimo1`` (1ª, 2ª parcela e 13º integral): a data de fim (competência
          do pagamento, vence no dia 20 do mês seguinte) dentro da janela, sem
          filtro por ano de R: a rescisão de janeiro soma o 13º de dezembro.

        Limite: o extrato posicionado depois do dia 20 de R já traz R-1, e a
        base o soma de novo.
        """
        self.ensure_one()
        if not self.date_to or not de or not ate:
            return False
        inicio, fim, inicio_13, fim_13 = self._l10n_br_janela_base_multa()
        if tipo == "mensal":
            return de <= fim and ate >= inicio
        if tipo == "ferias":
            if self.l10n_br_fgts_saldo_conta:
                return inicio <= de <= fim
            return de <= fim and ate >= inicio
        if tipo == "decimo1":
            return inicio_13 <= ate <= fim_13
        return False

    def _l10n_br_tipo_integridade(self):
        """``mensal``, ``ferias``, ``decimo1`` ou None: o tipo na participação."""
        self.ensure_one()
        if self._l10n_br_eh_mensal():
            return "mensal"
        codigo = self.struct_id.code
        if codigo == "FERIAS":
            return "ferias"
        if codigo == "13_1PARCELA" or codigo in self._L10N_BR_ESTRUTURAS_13_COMPLETO:
            return "decimo1"
        return None

    def _l10n_br_holerites_da_base_multa(self, contract):
        """Holerites cujo FGTS entra na base da multa desta rescisão (TG-138 r2).

        Lei 8.036/90 art. 18 §1º; Decreto 99.684/90 art. 9º §1º. Do mesmo
        contrato, em vigor e não cancelados: mensais, recibos de férias e 13º
        CONFIRMADO (rascunho não pagou nada, TG-97) que
        ``_l10n_br_entra_na_base_multa`` aceita.
        """
        self.ensure_one()
        slips = self.env["hr.payslip"]
        if not self.date_from or not self.date_to or not contract:
            return slips
        inicio, fim, inicio_13, fim_13 = self._l10n_br_janela_base_multa()
        candidatos = slips.search(
            [
                ("contract_id", "=", contract.id),
                ("id", "!=", self.id),
                ("state", "!=", "cancel"),
                ("l10n_br_fora_de_vigor", "=", False),
                ("date_to", ">=", min(inicio, inicio_13)),
                ("date_from", "<=", max(fim, fim_13)),
            ]
        )
        return candidatos.filtered(
            lambda slip: slip._l10n_br_tipo_integridade()
            and (slip.state == "done" or slip._l10n_br_tipo_integridade() != "decimo1")
            and self._l10n_br_entra_na_base_multa(
                slip._l10n_br_tipo_integridade(), slip.date_from, slip.date_to
            )
        )

    def _l10n_br_fgts_depositado_mensal(self, contract):
        """FGTS dos holerites MENSAIS e RECIBOS DE FÉRIAS da base da multa.

        Subconjunto de ``_l10n_br_holerites_da_base_multa`` (o depósito de R
        entra mesmo quando o mensal foi quem o fez e a rescisão o compensou no
        saldo de salário; com o saldo informado, o de R-1 também). Sem
        holerite na janela, devolve 0.
        """
        self.ensure_one()
        slips = self._l10n_br_holerites_da_base_multa(contract).filtered(
            lambda slip: slip._l10n_br_tipo_integridade() in ("mensal", "ferias")
        )
        return sum(
            slips.mapped("line_ids")
            .filtered(lambda ln: ln.code == "FGTS")
            .mapped("total")
        )

    def _l10n_br_fgts_13_primeira_depositado(self, contract):
        """FGTS já recolhido nas parcelas do 13º do mesmo ano (TG-93, TG-97).

        Soma a linha ``FGTS`` dos holerites de 1ª e de 2ª parcela CONFIRMADOS
        e em vigor (sem estorno) do contrato, no ano deste holerite. A
        rescisão abate este valor do FGTS do 13º do ano (as parcelas já
        recolheram a parte delas) e a base da multa o soma de volta, porque o
        depósito existe na conta vinculada. Sem parcela paga, devolve 0.
        """
        self.ensure_one()
        if not self.date_to or not contract:
            return 0.0
        pagos = self._l10n_br_holerites_13_pagos(contract)
        return sum(
            pagos.mapped("line_ids")
            .filtered(lambda ln: ln.code == "FGTS")
            .mapped("total")
        )

    def _l10n_br_fgts_13_na_base_multa(self, contract):
        """FGTS das parcelas do 13º que a base da multa ainda deve somar (TG-138).

        Subconjunto de ``_l10n_br_holerites_da_base_multa``: com o saldo
        informado, só a parcela paga em R-1 ou R (a anterior já venceu e está no
        extrato), inclusive dezembro do ano anterior numa rescisão de janeiro;
        sem saldo (estimativa que não inclui o 13º), todo o FGTS do 13º do ano.
        """
        self.ensure_one()
        slips = self._l10n_br_holerites_da_base_multa(contract).filtered(
            lambda slip: slip._l10n_br_tipo_integridade() == "decimo1"
        )
        return sum(
            slips.mapped("line_ids")
            .filtered(lambda ln: ln.code == "FGTS")
            .mapped("total")
        )

    def _l10n_br_holerites_13_pagos(self, contract):
        """Holerites de 13º (1ª, 2ª parcela e 13º integral) confirmados do ano.

        Do mesmo contrato e do ano deste holerite, em vigor (sem estorno) e
        confirmados: o rascunho e o cancelado não pagaram nada (TG-97).
        """
        self.ensure_one()
        if not self.date_to or not contract:
            return self.env["hr.payslip"]
        ano = self.date_to.year
        return self.env["hr.payslip"].search(
            [
                ("contract_id", "=", contract.id),
                ("id", "!=", self.id),
                ("state", "=", "done"),
                ("l10n_br_fora_de_vigor", "=", False),
                (
                    "struct_id.code",
                    "in",
                    ("13_1PARCELA",) + self._L10N_BR_ESTRUTURAS_13_COMPLETO,
                ),
                ("date_to", ">=", date(ano, 1, 1)),
                ("date_to", "<=", date(ano, 12, 31)),
            ]
        )

    def _l10n_br_decimo_pago_ano(self, contract):
        """O 13º que o contrato já recebeu no ano deste holerite (TG-97).

        - ``adiantamento``: a 1ª parcela paga SEM 2ª parcela confirmada. É o
          adiantamento do TRCT: sai como desconto próprio da rescisão, que
          paga o 13º proporcional inteiro.
        - ``quitado``: o bruto do 13º já fechado pela 2ª parcela (ou 13º
          integral) confirmada, que já abate a 1ª parcela. A rescisão paga só
          a diferença dos avos.
        - ``inss``, ``irrf`` e ``pensao``: o retido nessas apurações, que a
          rescisão desconta do imposto do total do ano.
        """
        self.ensure_one()
        res = {
            "adiantamento": 0.0,
            "quitado": 0.0,
            "inss": 0.0,
            "irrf": 0.0,
            "pensao": 0.0,
        }
        pagos = self._l10n_br_holerites_13_pagos(contract)
        completos = pagos.filtered(
            lambda s: s.struct_id.code in self._L10N_BR_ESTRUTURAS_13_COMPLETO
        )

        def total(slips, codigo):
            return sum(
                slips.mapped("line_ids")
                .filtered(lambda ln: ln.code == codigo)
                .mapped("total")
            )

        if completos:
            res["quitado"] = total(completos, "DECIMO_TERCEIRO_BRUTO")
            res["inss"] = total(completos, "INSS_13")
            res["irrf"] = total(completos, "IRRF_13")
            res["pensao"] = total(completos, "PENSAO_ALIMENTICIA_13")
        else:
            res["adiantamento"] = total(pagos, "ADIANTAMENTO_13")
        return res

    def _l10n_br_pensao_13_devolvida(self, pensao_paga, pensao_devida):
        """Pensão do 13º que volta ao empregado quando a 2ª parcela reteve a mais.

        Hoje, nenhuma (TG-141#P1, opção recomendada): a pensão retida foi
        repassada ao beneficiário por ordem judicial e alimentos pagos não se
        repetem; devolvê-la seria custo definitivo da empresa. Só INSS e IRRF
        voltam (``DEVOLUCAO_INSS_13`` e ``DEVOLUCAO_IRRF_13``) e a base do IRRF
        do 13º deduz a pensão efetivamente paga. Se a decisão for devolver,
        troque o retorno por ``max(pensao_paga - pensao_devida, 0.0)`` e some
        essa devolução ao NET e ao disponível do ``DESCONTO_13_EXCESSO``.
        """
        return 0.0

    def _l10n_br_impostos_13_mantido(
        self, br, employee, pago, desconto, pensao_rescisao
    ):
        """INSS e IRRF devidos sobre o 13º que o empregado mantém (TG-141).

        O 13º mantido é o quitado menos o ``desconto`` do excesso. O INSS é o
        da tabela sobre ele; o IRRF usa a base ``mantido - INSS - dependentes
        - pensão paga`` (nunca negativa, a pensão é a efetivamente paga, ver
        ``_l10n_br_pensao_13_devolvida``) e a forma mais favorável da regra.
        ``pago`` é ``_l10n_br_decimo_pago_ano``. Devolve ``(inss, irrf)`` sem
        arredondar.
        """
        mantido = max(pago["quitado"] - desconto, 0.0)
        inss = br.calc_inss(mantido)
        irrf = 0.0
        if not employee.l10n_br_molestia_grave:
            pensao_devida = br.calc_pensao_alimenticia(
                mantido, 0.0, employee.l10n_br_pensao_percentual
            )
            pensao_ano = (
                pago["pensao"]
                + pensao_rescisao
                - self._l10n_br_pensao_13_devolvida(pago["pensao"], pensao_devida)
            )
            dependentes = (
                employee.l10n_br_irrf_dependentes * br.irrf_deducao_dependente()
            )
            base_irrf = max(mantido - inss - dependentes - pensao_ano, 0.0)
            irrf = br.irrf_mais_favoravel(mantido, base_irrf)
        return inss, irrf

    def _l10n_br_creditos_13(
        self, br, contract, employee, desconto, pensao_rescisao, pago=None
    ):
        """INSS e IRRF do 13º a devolver quando a rescisão desconta ``desconto``.

        A devolução de cada imposto é o retido nas parcelas menos o imposto
        sobre o 13º que o empregado mantém (``_l10n_br_impostos_13_mantido``).
        Exata, não proporcional: desconto zero devolve zero e o excesso inteiro
        devolve tudo o que passa do imposto sobre o devido.

        ``br`` é o ``tools.br`` da regra. Devolve ``(inss, irrf)`` arredondados.
        """
        self.ensure_one()
        pago = pago or self._l10n_br_decimo_pago_ano(contract)
        inss, irrf = self._l10n_br_impostos_13_mantido(
            br, employee, pago, desconto, pensao_rescisao
        )
        return (
            br.round_money(max(pago["inss"] - inss, 0.0)),
            br.round_money(max(pago["irrf"] - irrf, 0.0)),
        )

    def _l10n_br_creditos_restantes_13(
        self, br, contract, employee, desconto, devido, pensao_rescisao
    ):
        """INSS e IRRF ainda retidos sobre a parte do excesso NÃO descontada.

        ``imposto(quitado - desconto) - imposto(quitado - excesso)``, pela
        mesma função exata da devolução (``quitado - excesso`` é o devido).
        Informativo: se o empregado pagar a parte não descontada, o DP retifica
        o S-2299 com o desconto e as devoluções do restante (MOS S-1.3, item
        15.2). Devolve ``(inss, irrf)`` arredondados, nunca negativos.
        """
        self.ensure_one()
        pago = self._l10n_br_decimo_pago_ano(contract)
        excesso = max(pago["quitado"] - devido, 0.0)
        inss_d, irrf_d = self._l10n_br_impostos_13_mantido(
            br, employee, pago, desconto, pensao_rescisao
        )
        inss_e, irrf_e = self._l10n_br_impostos_13_mantido(
            br, employee, pago, excesso, pensao_rescisao
        )
        return (
            br.round_money(max(inss_d - inss_e, 0.0)),
            br.round_money(max(irrf_d - irrf_e, 0.0)),
        )

    def _l10n_br_desconto_excesso_13(
        self, br, contract, employee, devido, disponivel, teto, pensao_rescisao
    ):
        """Maior desconto do 13º pago a mais que o líquido e o teto comportam.

        O desconto ``d`` limita-se ao excesso (quitado - devido), ao teto de um
        mês de remuneração menos as outras compensações (``teto``, CLT art.
        477, §5º) e ao líquido: ``d - devolução(d) <= disponivel``, onde a
        devolução (``_l10n_br_creditos_13``) cresce com ``d``. A circularidade
        (o líquido conta a devolução, que depende de ``d``) se resolve sem
        laço infinito: a diferença ``d - devolução(d)`` é crescente em ``d``
        (a alíquota marginal dos dois impostos somados é menor que 1), então
        uma busca binária sobre centavos inteiros acha o maior ``d`` que cabe.
        Como cada devolução é arredondada, a diferença pode descer 1 ou 2
        centavos em alguns pontos: o resultado pode ficar até cerca de 3
        centavos abaixo do máximo teórico, mas NUNCA acima do que cabe: só se
        aceita um valor que ``cabe`` (o líquido nunca fica negativo, nem em
        -0,01).
        """
        self.ensure_one()
        pago = self._l10n_br_decimo_pago_ano(contract)
        excesso = br.round_money(pago["quitado"] - devido)
        maximo = int(round(max(min(excesso, teto), 0.0) * 100))
        if maximo <= 0 or disponivel <= 0:
            return 0.0
        livre = int(round(disponivel * 100))

        def cabe(centavos):
            inss, irrf = self._l10n_br_creditos_13(
                br, contract, employee, centavos / 100.0, pensao_rescisao, pago
            )
            custo = centavos - int(round(inss * 100)) - int(round(irrf * 100))
            return custo <= livre

        if cabe(maximo):
            return maximo / 100.0
        baixo, alto = 0, maximo  # cabe(baixo); não cabe(alto)
        while alto - baixo > 1:
            meio = (baixo + alto) // 2
            if cabe(meio):
                baixo = meio
            else:
                alto = meio
        return baixo / 100.0

    def _l10n_br_aviso_indenizado_devido(self):
        """Aviso prévio indenizado é devido pelo empregador (RF-06).

        Só em rescisão sem justa causa ou por acordo (CLT art. 484-A), e só
        quando marcado como INDENIZADO (o trabalhado já foi pago na folha
        mensal do próprio período de aviso).
        """
        self.ensure_one()
        return (
            self._l10n_br_fator_rescisao("aviso") > 0
            and self.l10n_br_aviso_previo == "indenizado"
        )

    def _l10n_br_regra_rescisao(self):
        self.ensure_one()
        return L10N_BR_REGRAS_RESCISAO.get(
            self.l10n_br_tipo_rescisao, L10N_BR_REGRA_RESCISAO_PADRAO
        )

    def _l10n_br_fator_rescisao(self, verba):
        """Fração devida da verba ('aviso', 'decimo' ou 'ferias') na causa."""
        return self._l10n_br_regra_rescisao()[verba]

    def _l10n_br_percentual_multa_fgts(self):
        """Percentual da multa do FGTS da causa (0, 0.20 ou 0.40)."""
        return self._l10n_br_regra_rescisao()["multa"]

    def _l10n_br_motivo_desligamento_esocial(self):
        """``mtvDeslig`` (tabela 19) da causa; False se não houver tipo."""
        return self._l10n_br_regra_rescisao()["mtv"]

    @staticmethod
    def _l10n_br_dias_comerciais(inicio, fim):
        """Dias entre duas datas no mês comercial de 30 dias (ano de 360).

        O último dia de cada mês conta como dia 30: de 30/09 a 31/10 são 30 dias,
        o mês inteiro, e não os 31 corridos.
        """

        def dia(data):
            ultimo = data + relativedelta(day=31)
            return 30 if data == ultimo else data.day

        return (
            (fim.year - inicio.year) * 360
            + (fim.month - inicio.month) * 30
            + dia(fim)
            - dia(inicio)
        )

    def _l10n_br_dias_restantes_termo(self):
        """Dias comerciais do desligamento até o termo do contrato."""
        self.ensure_one()
        if not (self.l10n_br_data_termo_contrato and self.date_to):
            return 0
        return max(
            self._l10n_br_dias_comerciais(
                self.date_to, self.l10n_br_data_termo_contrato
            ),
            0,
        )

    def _l10n_br_indenizacao_art_479(self, remuneracao_mensal):
        """Metade da remuneração dos dias que faltavam até o termo (CLT art. 479).

        Mês comercial de 30 dias (ver ``_l10n_br_dias_comerciais``). Sem
        arredondar: a regra salarial arredonda o valor.
        """
        self.ensure_one()
        dias = self._l10n_br_dias_restantes_termo()
        return remuneracao_mensal / 30 * dias / 2

    def _l10n_br_desconto_art_480(self, remuneracao_mensal):
        """Indenização do empregado ao empregador (CLT art. 480).

        O prejuízo informado, limitado ao que o empregado receberia pelo art. 479
        (art. 480, §1º) e a um mês de remuneração (art. 477, §5º).
        """
        self.ensure_one()
        return min(
            self.l10n_br_prejuizo_art_480,
            self._l10n_br_indenizacao_art_479(remuneracao_mensal),
            remuneracao_mensal,
        )

    def _l10n_br_data_projetada_rescisao(self):
        """Data de referência para 13º/férias proporcionais na rescisão.

        Súmula 371 TST: a projeção do aviso prévio indenizado é considerada
        para o 13º salário e as férias proporcionais (mas não para as
        demais verbas rescisórias). Fora da rescisão (ou sem aviso
        indenizado), a referência é o próprio ``date_to``.
        """
        self.ensure_one()
        if self.date_to and self._l10n_br_aviso_indenizado_devido():
            dias = self._l10n_br_dias_aviso_previo()
            return self.date_to + relativedelta(days=dias)
        return self.date_to

    def _l10n_br_ferias_vencidas_dados(self):
        """Períodos aquisitivos VENCIDOS e não gozados até a rescisão.

        CLT art. 146: na cessação do contrato, qualquer que seja a causa,
        são devidas as férias de período aquisitivo já COMPLETO e ainda não
        gozado ("vencidas") - diferente das proporcionais do período em
        curso (``l10n_br_avos_ferias``). CLT art. 137: pagas após o período
        concessivo (os 12 meses seguintes ao término do período aquisitivo,
        CLT art. 134), o pagamento é em DOBRO.

        "Não gozado" é apurado pelos holerites de férias CONFIRMADOS
        (state == "done") já vinculados à mesma alocação
        (``l10n_br_ferias_allocation_id``): dias de direito menos os já
        pagos (gozados + vendidos) em qualquer fração anterior.

        TG-147: com aviso prévio indenizado o contrato é projetado até
        ``_l10n_br_data_projetada_rescisao`` (Súmula 371 TST, CLT art. 487
        § 1º): o período aquisitivo que se completa dentro da projeção também
        é vencido, pago inteiro. A fonte do período é a mesma alocação do
        ``hr_holidays``; os avos proporcionais recomeçam no aniversário
        (``_calc_avos_ferias_proporcionais``), sem sobreposição. Esse período
        nunca é em dobro: o concessivo dele termina depois do desligamento.

        Returns:
            list[dict]: ``[{"dias": int, "dobro": bool, "inicio": date,
            "fim": date}, ...]``, um item por período aquisitivo vencido com
            saldo residual (``inicio`` e ``fim`` são os da alocação).
        """
        self.ensure_one()
        if not self.employee_id or not self.date_to:
            return []
        vacation_type = self.env.ref(
            "l10n_br_hr_vacation.leave_type_ferias", raise_if_not_found=False
        )
        if not vacation_type:
            return []
        allocations = self.env["hr.leave.allocation"].search(
            [
                ("employee_id", "=", self.employee_id.id),
                ("holiday_status_id", "=", vacation_type.id),
                ("state", "=", "validate"),
                ("date_to", "!=", False),
                ("date_to", "<=", self._l10n_br_data_projetada_rescisao()),
            ]
        )
        resultado = []
        for alloc in allocations:
            pagos = self.env["hr.payslip"].search(
                [
                    ("l10n_br_ferias_allocation_id", "=", alloc.id),
                    ("state", "=", "done"),
                    ("l10n_br_fora_de_vigor", "=", False),
                ]
            )
            dias_pagos = sum(pagos.mapped("l10n_br_dias_periodo_gozado")) + sum(
                pagos.mapped("l10n_br_dias_abono")
            )
            restante = alloc.number_of_days - dias_pagos
            if restante > 0:
                periodo_concessivo_fim = alloc._l10n_br_fim_concessivo()
                dobro = self.date_to > periodo_concessivo_fim
                resultado.append(
                    {
                        "dias": restante,
                        "dobro": dobro,
                        "inicio": alloc.date_from,
                        "fim": alloc.date_to,
                    }
                )
        return resultado

    @api.depends("line_ids", "l10n_br_primeira_parcela_13_paga")
    def _compute_liquido_13(self):
        for rec in self:
            bruto = sum(
                rec.line_ids.filtered(
                    lambda line: line.code == "DECIMO_TERCEIRO_BRUTO"
                ).mapped("total")
            )
            inss_13 = sum(
                rec.line_ids.filtered(lambda line: line.code == "INSS_13").mapped(
                    "total"
                )
            )
            irrf_13 = sum(
                rec.line_ids.filtered(lambda line: line.code == "IRRF_13").mapped(
                    "total"
                )
            )
            rec.l10n_br_liquido_13 = (
                bruto - inss_13 - irrf_13 - rec.l10n_br_primeira_parcela_13_paga
            )

    def _get_baselocaldict(self, contracts):
        localdict = super()._get_baselocaldict(contracts)
        for code in (
            "FERIAS",
            "ADICIONAL_FERIAS",
            "ABONO_PECUNIARIO",
            "ADICIONAL_ABONO",
            "DECIMO_TERCEIRO_BRUTO",
            "ADIANTAMENTO_13",
            "INSS_13",
            "IRRF_13",
            "BASE_IRRF_13",
            # Pensão retida sobre a apuração exclusiva do 13º (RF-03): a base
            # do IRRF do 13º a referencia mesmo quando o empregado não tem
            # pensão (regra condicional que não dispara).
            "PENSAO_ALIMENTICIA_13",
            "DECIMO_RESCISAO",
            # TG-136: 13º sobre o aviso prévio indenizado, em rubrica própria.
            "DECIMO_AVISO_INDENIZADO",
            "SALDO_SALARIO",
            "FERIAS_INDENIZADAS",
            "ADICIONAL_FERIAS_INDENIZADAS",
            # RF-06: verbas rescisórias novas (aviso, multa do FGTS, férias
            # vencidas) - pré-populadas para as regras condicionais que
            # referenciam estes códigos quando a verba não é devida.
            "FERIAS_VENCIDAS",
            "ADICIONAL_FERIAS_VENCIDAS",
            "AVISO_PREVIO_INDENIZADO",
            # TG-96: indenização do art. 479 e descontos dos arts. 480 e 487 §2º.
            "INDENIZACAO_ART_479",
            "DESCONTO_ART_480",
            "DESCONTO_AVISO_PREVIO",
            "NAO_DESCONTADO_ADIANTAMENTO_13",
            # TG-141: 13º devido (base única dos encargos do 13º), devolução dos
            # encargos retidos a mais e desconto do 13º pago além do devido.
            "DECIMO_DEVIDO",
            "DEVOLUCAO_INSS_13",
            "DEVOLUCAO_IRRF_13",
            "DESCONTO_13_EXCESSO",
            # TG-141#P2: linhas informativas do que ficou sem descontar.
            "NAO_DESCONTADO_13_EXCESSO",
            "CREDITO_INSS_13_RESTANTE",
            "CREDITO_IRRF_13_RESTANTE",
            "FGTS_AVISO",
            "FGTS",
            "FGTS_13",
            "MULTA_FGTS",
        ):
            localdict.setdefault(code, 0.0)
        return localdict


class HrPayslipLine(models.Model):
    _inherit = "hr.payslip.line"

    def write(self, vals):
        slips = self.mapped("slip_id")
        if not slips or self.env.context.get("l10n_br_em_compute"):
            return super().write(vals)
        # TG-138: o write direto na linha (FGTS ou salário do mensal, base do
        # recibo) passa pelo mesmo ponto único de integridade do holerite.
        antes = slips._l10n_br_participacao()
        res = super().write(vals)
        slips._l10n_br_reconciliar_participacao(antes, slips._l10n_br_participacao())
        return res

    @api.model_create_multi
    def create(self, vals_list):
        slips = self.env["hr.payslip"].browse(
            {vals["slip_id"] for vals in vals_list if vals.get("slip_id")}
        )
        if not slips or self.env.context.get("l10n_br_em_compute"):
            return super().create(vals_list)
        # TG-138 r2: linha criada direto num holerite existente passa pelo mesmo
        # ponto de integridade (compute_sheet já confere no fim).
        antes = slips._l10n_br_participacao()
        lines = super().create(vals_list)
        slips._l10n_br_reconciliar_participacao(antes, slips._l10n_br_participacao())
        return lines

    def unlink(self):
        slips = self.mapped("slip_id").filtered(
            lambda s: s._l10n_br_eh_mensal() or s.struct_id.code == "FERIAS"
        )
        if not slips or self.env.context.get("l10n_br_em_compute"):
            # compute_sheet(): a conferência é do próprio compute_sheet.
            return super().unlink()
        antes = slips._l10n_br_participacao()
        res = super().unlink()
        slips._l10n_br_reconciliar_participacao(antes, slips._l10n_br_participacao())
        return res
