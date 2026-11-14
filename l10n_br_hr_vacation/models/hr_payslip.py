# Copyright 2024 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from datetime import date, timedelta

from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

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
    l10n_br_dias_ferias_gozadas = fields.Integer(
        string="Dias de Férias Gozadas",
        compute="_compute_dias_ferias_gozadas",
    )
    l10n_br_avos_13 = fields.Integer(
        string="Avos de 13º",
        compute="_compute_avos_13",
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
        "rescisão: o depósito do mês é somado pela regra. Não aceita valor "
        "negativo. Zero e em branco são a mesma coisa: a "
        "regra usa o FALLBACK 8% x salário x meses trabalhados - uma "
        "ESTIMATIVA sem juros/correção monetária, que subestima o saldo "
        "real; preencher com o extrato sempre que disponível.",
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
        dependentes = (mensais | rescisoes) - self
        fechados = dependentes.filtered(lambda r: r.state not in ("draft", "verify"))
        if fechados:
            raise UserError(
                _(
                    "Não é possível alterar este holerite: %(fechados)s, do mesmo "
                    "contrato e período, já está confirmado e depende dele (dias "
                    "de férias, salário ou saldo compensado). Volte o confirmado "
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
        return slips

    def write(self, vals):
        if (
            not self
            or self.env.context.get("l10n_br_em_compute")
            or not set(vals) & set(self._L10N_BR_CAMPOS_PARTICIPACAO)
        ):
            return super().write(vals)
        antes = self._l10n_br_participacao()
        res = super().write(vals)
        self._l10n_br_reconciliar_participacao(antes, self._l10n_br_participacao())
        return res

    def unlink(self):
        antes = self._l10n_br_participacao()
        res = super().unlink()
        self.browse()._l10n_br_reconciliar_participacao(antes, {})
        return res

    def compute_sheet(self):
        # O compute_sheet apaga as linhas e grava as novas: a conferência é uma
        # só, no fim, contra a participação de antes (variável local).
        antes = self._l10n_br_participacao()
        res = super(
            HrPayslip, self.with_context(l10n_br_em_compute=True)
        ).compute_sheet()
        self._l10n_br_reconciliar_participacao(antes, self._l10n_br_participacao())
        return res

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
            else:
                rec.l10n_br_avos_13 = 0

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
        """Dias de aviso prévio devidos (Lei 12.506/2011). Ver salary_rules_br."""
        self.ensure_one()
        if not self.contract_id or not self.contract_id.date_start or not self.date_to:
            return 0
        from odoo.addons.l10n_br_hr_payroll.models.salary_rules_br import (
            calc_aviso_previo_dias,
        )

        return calc_aviso_previo_dias(self.contract_id.date_start, self.date_to)

    def _l10n_br_fgts_depositado_mensal(self, contract):
        """FGTS já depositado nos holerites MENSAIS do mesmo período (sem cancelados).

        Base da multa (Decreto 99.684/90, art. 9º, § 1º): o depósito do mês da
        rescisão entra mesmo quando foi feito pelo mensal e a rescisão o
        compensou no saldo de salário (mesmo conjunto de holerites de
        ``_l10n_br_salario_pago_mensal``). Sem mensal sobreposto, devolve 0.
        """
        self.ensure_one()
        if not self.date_from or not self.date_to:
            return 0.0
        mensais = self.env["hr.payslip"].search(
            [
                ("contract_id", "=", contract.id),
                ("id", "!=", self.id),
                ("state", "!=", "cancel"),
                ("l10n_br_fora_de_vigor", "=", False),
                ("struct_id", "in", self._l10n_br_estruturas_mensais().ids),
                ("date_from", "<=", self.date_to),
                ("date_to", ">=", self.date_from),
            ]
        )
        return sum(
            mensais.mapped("line_ids")
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

        Returns:
            list[dict]: ``[{"dias": int, "dobro": bool}, ...]``, um item por
            período aquisitivo vencido com saldo residual.
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
                ("date_to", "<=", self.date_to),
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
                periodo_concessivo_fim = alloc.date_to + relativedelta(years=1)
                dobro = self.date_to > periodo_concessivo_fim
                resultado.append({"dias": restante, "dobro": dobro})
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
            "FGTS_AVISO",
            "FGTS",
            "FGTS_13",
            "MULTA_FGTS",
        ):
            localdict.setdefault(code, 0.0)
        return localdict


class HrPayslipLine(models.Model):
    _inherit = "hr.payslip.line"

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
