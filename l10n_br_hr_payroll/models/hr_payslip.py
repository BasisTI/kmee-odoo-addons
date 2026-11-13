# Copyright 2024 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import logging
import types
from datetime import timedelta

import pytz
from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

from . import salary_rules_br

_logger = logging.getLogger(__name__)


class HrPayslip(models.Model):
    _inherit = "hr.payslip"

    l10n_br_horas_extras_50 = fields.Float(
        string="Horas Extras 50%",
        help="Horas extras em dias úteis",
    )
    l10n_br_horas_extras_100 = fields.Float(
        string="Horas Extras 100%",
        help="Horas extras em domingos/feriados",
    )
    l10n_br_horas_noturnas = fields.Float(
        string="Horas Noturnas",
        help="Horas de relógio trabalhadas entre 22h e 05h (60 minutos cada), "
        "sem a conversão pela hora reduzida: ela é feita uma vez só, em "
        "Horas Noturnas Computadas.",
    )
    l10n_br_usar_hora_reduzida = fields.Boolean(
        string="Usar Hora Noturna Reduzida",
        default=True,
        help="Hora noturna = 52min30s: cada hora de relógio noturna conta como "
        "60/52,5 = 8/7 de hora (CLT, art. 73, § 1º). A conversão incide sobre as "
        "Horas Noturnas, que são de relógio. Vem do contrato (campo Hora Noturna "
        "Reduzida) ao criar o holerite e enquanto ele está em rascunho; holerite "
        "confirmado ou pago guarda o que valeu no cálculo.",
    )
    l10n_br_horas_noturnas_computadas = fields.Float(
        string="Horas Noturnas Computadas",
        compute="_compute_horas_noturnas_computadas",
        help="Horas noturnas já convertidas pela hora reduzida (relógio x 8/7); "
        "é a quantidade sobre a qual incide o adicional noturno.",
    )
    l10n_br_faltas_injustificadas = fields.Integer(
        string="Faltas Injustificadas",
        default=0,
    )
    l10n_br_falta_ids = fields.One2many(
        "l10n_br.hr.payslip.falta",
        "payslip_id",
        string="Dias de falta",
        help="Datas das faltas injustificadas. Com a data, o DSR é descontado "
        "uma vez por semana com falta; falta sem data conta numa semana própria.",
    )

    # O OCA copia ``credit_note`` e ``refunded_id`` em qualquer "Duplicar": a
    # cópia de um estornado nasceria "estornado" (e a de um estorno, estorno), fora
    # de vigor sem estorno nenhum. Só o ``refund_sheet`` os grava (``credit_note``
    # vai explícito no ``default`` da cópia; o vínculo, depois da cópia).
    credit_note = fields.Boolean(copy=False)
    refunded_id = fields.Many2one(copy=False)
    l10n_br_estorno = fields.Boolean(
        string="Holerite de estorno",
        readonly=True,
        copy=False,
        help="Marcado só pela Devolução. Diferente de ``credit_note``, que o "
        "usuário alcança no rascunho, este não é deduzido de campo editável.",
    )
    l10n_br_fora_de_vigor = fields.Boolean(
        string="Estorno ou estornado",
        compute="_compute_l10n_br_fora_de_vigor",
        store=True,
        help="Marca o holerite de estorno (devolução) e o holerite original "
        "que tem um estorno em vigor: o par se anula e nenhum dos dois conta "
        "para período duplicado, DSR, médias, salário já pago ou integridade "
        "entre holerites. O estorno não pode ser cancelado.",
    )

    @api.depends("l10n_br_estorno", "refunded_id", "refunded_id.state")
    def _compute_l10n_br_fora_de_vigor(self):
        for slip in self:
            slip.l10n_br_fora_de_vigor = bool(
                slip.l10n_br_estorno
                or (slip.refunded_id and slip.refunded_id.state != "cancel")
            )

    def copy_data(self, default=None):
        if self.env.context.get("l10n_br_estornando"):
            default = dict(default or {}, l10n_br_estorno=True)
        return super().copy_data(default)

    def _l10n_br_estorno_dependentes(self):
        """Holerites de média (férias, 13º, rescisão) que leem os mensais daqui.

        Os que ficam depois do mensal, dentro da janela de 12 meses de
        ``_l10n_br_media_habitual``, na mesma relação de contrato.
        """
        dependentes = self.browse()
        for slip in self.filtered(lambda s: s.date_from and s._l10n_br_eh_mensal()):
            dependentes |= (
                self.sudo()
                .search(
                    [
                        ("contract_id", "=", slip.contract_id.id),
                        ("state", "!=", "cancel"),
                        ("l10n_br_fora_de_vigor", "=", False),
                        ("date_from", ">", slip.date_from),
                        ("date_from", "<=", slip.date_from + relativedelta(months=12)),
                    ]
                )
                .filtered(lambda r: not r._l10n_br_eh_mensal())
            )
        return dependentes - self

    def refund_sheet(self):
        """Devolução: só do confirmado em vigor, uma vez, e com as médias em dia."""
        for slip in self:
            if slip.l10n_br_estorno or slip.credit_note:
                raise UserError(
                    _(
                        "O holerite %(slip)s já é um estorno: não se estorna um "
                        "estorno.",
                        slip=slip.number or slip.name,
                    )
                )
            if slip.refunded_id and slip.refunded_id.state != "cancel":
                raise UserError(
                    _(
                        "O holerite %(slip)s já foi estornado por %(estorno)s.",
                        slip=slip.number or slip.name,
                        estorno=slip.refunded_id.number or slip.refunded_id.name,
                    )
                )
        dependentes = self._l10n_br_estorno_dependentes()
        fechados = dependentes.filtered(lambda r: r.state not in ("draft", "verify"))
        if fechados:
            raise UserError(
                _(
                    "Não é possível estornar: %(fechados)s, do mesmo contrato, já "
                    "está confirmado e a média dele depende deste holerite. Volte o "
                    "confirmado para rascunho primeiro.",
                    fechados=", ".join(fechados.mapped(lambda r: r.number or r.name)),
                )
            )
        res = super(
            HrPayslip, self.with_context(l10n_br_estornando=True)
        ).refund_sheet()
        # As médias que liam o estornado: quem nunca foi calculado será certo no
        # 1º cálculo.
        dependentes.filtered("line_ids").compute_sheet()
        return res

    @api.constrains("l10n_br_faltas_injustificadas", "l10n_br_falta_ids")
    def _check_datas_faltas(self):
        for rec in self:
            if len(rec.l10n_br_falta_ids) > rec.l10n_br_faltas_injustificadas:
                raise ValidationError(
                    _(
                        "Há %(datas)s datas de falta para %(faltas)s faltas "
                        "injustificadas no holerite.",
                        datas=len(rec.l10n_br_falta_ids),
                        faltas=rec.l10n_br_faltas_injustificadas,
                    )
                )

    @api.constrains(
        "l10n_br_faltas_injustificadas", "l10n_br_falta_ids", "date_from", "date_to"
    )
    def _check_datas_faltas_periodo(self):
        """Datas das faltas dentro do período (que pode ser alterado depois)."""
        for rec in self:
            fora = rec.l10n_br_falta_ids.filtered(
                lambda f: f._l10n_br_fora_do_periodo()
            )
            if fora:
                raise ValidationError(
                    _(
                        "A falta de %(dia)s está fora do período do holerite "
                        "(%(ini)s a %(fim)s).",
                        dia=fora[0].date,
                        ini=rec.date_from,
                        fim=rec.date_to,
                    )
                )

    @api.onchange("contract_id")
    def _onchange_contract_hora_reduzida(self):
        """A marca segue o contrato; no formulário ela é só de leitura."""
        for rec in self:
            if rec.contract_id:
                rec.l10n_br_usar_hora_reduzida = (
                    rec.contract_id.l10n_br_hora_noturna_reduzida
                )

    @api.depends("l10n_br_horas_noturnas", "l10n_br_usar_hora_reduzida")
    def _compute_horas_noturnas_computadas(self):
        """Converte as horas noturnas de relógio pela hora reduzida (art. 73, § 1º).

        Cada 52min30s de relógio valem uma hora de trabalho: 60 / 52,5 = 8/7
        (60 min de relógio = 1h08min34s computadas). O fator 7/8, usado antes,
        era o inverso e reduzia a quantidade em vez de aumentá-la.
        """
        for rec in self:
            if rec.l10n_br_usar_hora_reduzida:
                rec.l10n_br_horas_noturnas_computadas = (
                    rec.l10n_br_horas_noturnas * 8 / 7
                )
            else:
                rec.l10n_br_horas_noturnas_computadas = rec.l10n_br_horas_noturnas

    def compute_sheet(self):
        """Ensure worked_days_line_ids are populated before computing rules.

        OCA compute_sheet() only computes salary rule lines (line_ids).
        worked_days are normally populated by onchange handlers (UI) or the
        batch wizard, but NOT by compute_sheet itself. When payslips are
        created programmatically (tests, demo, API), worked_days are empty.
        This override fills them in if missing.
        """
        for payslip in self:
            if not payslip.worked_days_line_ids:
                contracts = payslip._get_employee_contracts()
                if contracts and payslip.date_from and payslip.date_to:
                    worked_days = payslip.get_worked_day_lines(
                        contracts, payslip.date_from, payslip.date_to
                    )
                    lines = [(0, 0, wd) for wd in worked_days]
                    payslip.write({"worked_days_line_ids": lines})
        # O compute_sheet também grava o que o DSR de outros holerites do
        # empregado pode depender (as faltas, no ponto; as férias): a
        # conferência é uma só, no fim, contra o "antes" (variável local).
        if self.env.context.get("l10n_br_dsr_reconciliando"):
            return super().compute_sheet()
        empregados = self.employee_id
        antes = self._l10n_br_dsr_participacao(empregados)
        res = super(
            HrPayslip, self.with_context(l10n_br_dsr_em_compute=True)
        ).compute_sheet()
        self._l10n_br_dsr_reconciliar(antes, self.employee_id | empregados, self)
        return res

    # ------------------------------------------------------------------
    # DSR por semana com falta: ponto único de reconciliação (TG-84)
    # ------------------------------------------------------------------
    # Uma semana com falta é descontada UMA vez só, no holerite que traz a
    # primeira falta válida dela. Logo, o que cada holerite do empregado
    # desconta depende dos outros. Em vez de enumerar gatilhos, compara-se,
    # antes e depois de qualquer gravação que possa mudar isso, quais semanas
    # cada holerite desconta: só os que mudaram são recalculados (rascunho e
    # verificação) ou recusam a gravação (já confirmados). O "antes" é variável
    # local: não sobrevive a rollback.

    _L10N_BR_CAMPOS_DSR = (
        "state",
        "l10n_br_estorno",
        "refunded_id",
        "employee_id",
        "contract_id",
        "date_from",
        "date_to",
        "struct_id",
        "line_ids",
        "l10n_br_faltas_injustificadas",
        "l10n_br_falta_ids",
        # Do l10n_br_hr_vacation: o gozo das férias tira dias das faltas.
        "l10n_br_dias_periodo_gozado",
        "l10n_br_ferias_allocation_id",
        "l10n_br_abono_pecuniario",
    )

    def _l10n_br_faltas_validas(self):
        """Faltas que valem: as que não caem em férias nem afastamento."""
        self.ensure_one()
        contrato = self.contract_id
        periodos = []
        if contrato:
            periodos = list(self._l10n_br_afastamentos_inss(contrato)) + list(
                self._l10n_br_ferias_gozadas(contrato)
            )
        return self.l10n_br_falta_ids.filtered(
            lambda f: not any(ini <= f.date <= fim for ini, fim in periodos)
        )

    @api.model
    def _l10n_br_dsr_participacao(self, empregados):
        """``{holerite: (semanas que desconta, faltas sem data)}`` dos empregados.

        Das semanas com falta válida, a descontada é a do holerite com a
        primeira falta (data e, no empate, o menor id). A falta sem data conta
        numa semana própria, no máximo uma por semana do período do holerite
        que ainda não tenha falta datada (critério conservador: nunca mais
        repousos do que semanas).
        """
        res = {}
        for empregado in empregados:
            slips = (
                self.sudo()
                .with_context(active_test=False)
                .search(
                    [
                        ("employee_id", "=", empregado.id),
                        ("state", "!=", "cancel"),
                        ("l10n_br_fora_de_vigor", "=", False),
                        "|",
                        ("l10n_br_falta_ids", "!=", False),
                        ("l10n_br_faltas_injustificadas", ">", 0),
                    ]
                )
            )
            validas = {slip.id: slip._l10n_br_faltas_validas() for slip in slips}
            # A falta tardia (de competência já fechada, lançada no mês
            # seguinte) só é dona da semana se nenhuma falta comum a tem: o
            # repouso não é descontado duas vezes.
            primeira = {}
            for slip in slips:
                for falta in validas[slip.id]:
                    sem = salary_rules_br.inicio_semana(falta.date)
                    chave = (falta.tardia, falta.date, slip.id)
                    if sem not in primeira or chave < primeira[sem]:
                        primeira[sem] = chave
            for slip in slips:
                proprias = {
                    salary_rules_br.inicio_semana(f.date) for f in validas[slip.id]
                }
                donas = frozenset(s for s in proprias if primeira[s][2] == slip.id)
                sem_data = max(
                    slip.l10n_br_faltas_injustificadas - len(slip.l10n_br_falta_ids), 0
                )
                if slip.date_from and slip.date_to:
                    # Semanas do período que nenhuma falta datada (deste ou de
                    # outro holerite) já ocupa: só nelas cabe falta sem data.
                    semanas = set()
                    dia = salary_rules_br.inicio_semana(slip.date_from)
                    while dia <= slip.date_to:
                        semanas.add(dia)
                        dia += timedelta(days=7)
                    livres = len(semanas - set(primeira))
                    sem_data = min(sem_data, livres)
                res[slip.id] = (donas, sem_data)
        return res

    def _l10n_br_dsr_reconciliar(self, antes, empregados, proprios):
        """Recalcula/recusa os holerites cujo DSR mudou, fora ``proprios``."""
        if self.env.context.get("l10n_br_dsr_reconciliando"):
            return
        depois = self._l10n_br_dsr_participacao(empregados)
        mudaram = {i for i in set(antes) | set(depois) if antes.get(i) != depois.get(i)}
        dependentes = self.sudo().browse(sorted(mudaram)).exists() - proprios.sudo()
        dependentes = dependentes.filtered(lambda r: r.state != "cancel")
        fechados = dependentes.filtered(lambda r: r.state not in ("draft", "verify"))
        if fechados:
            raise UserError(
                _(
                    "Não é possível alterar este holerite, falta, recibo de férias "
                    "ou afastamento: %(fechados)s, do mesmo empregado, já está "
                    "confirmado e o desconto de DSR da semana depende dele. Volte "
                    "o confirmado para rascunho primeiro.",
                    fechados=", ".join(fechados.mapped(lambda r: r.number or r.name)),
                )
            )
        # Quem nunca foi calculado não tem DSR a corrigir: será certo no 1º cálculo.
        dependentes.filtered("line_ids").with_context(
            l10n_br_dsr_reconciliando=True
        ).compute_sheet()

    def _l10n_br_recusar_cancelar_estorno(self):
        estornos = self.filtered("l10n_br_estorno")
        if estornos:
            raise UserError(
                _(
                    "O holerite de estorno %(estornos)s não pode ser cancelado: "
                    "quem errou o estorno calcula um holerite novo.",
                    estornos=", ".join(estornos.mapped(lambda r: r.number or r.name)),
                )
            )

    def action_payslip_cancel(self):
        self._l10n_br_recusar_cancelar_estorno()
        return super().action_payslip_cancel()

    @api.model_create_multi
    def create(self, vals_list):
        # Criar um holerite (o recibo de férias que cobre o dia de uma falta)
        # também muda o que os outros holerites do empregado descontam de DSR.
        if self.env.context.get("l10n_br_dsr_reconciliando"):
            return super().create(vals_list)
        empregados = self.env["hr.employee"].browse(
            [v["employee_id"] for v in vals_list if v.get("employee_id")]
        )
        antes = self._l10n_br_dsr_participacao(empregados)
        vals_list = [dict(v) for v in vals_list]
        for vals in vals_list:
            if vals.get("state") == "cancel":
            self._l10n_br_recusar_cancelar_estorno()
        if (
            not self
            or self.env.context.get("l10n_br_dsr_em_compute")
            or self.env.context.get("l10n_br_dsr_reconciliando")
            or not set(vals) & set(self._L10N_BR_CAMPOS_DSR)
        ):
            return super().write(vals)
        if "l10n_br_faltas_injustificadas" in vals and "l10n_br_falta_ids" in vals:
            # A contagem antes das datas: a conferência "datas <= faltas" das
            # linhas novas lê a contagem já gravada.
            vals = {
                "l10n_br_faltas_injustificadas": vals["l10n_br_faltas_injustificadas"],
                **vals,
            }
        empregados = self.employee_id
        antes = self._l10n_br_dsr_participacao(empregados)
        res = super().write(vals)
        self._l10n_br_dsr_reconciliar(antes, self.employee_id | empregados, self)
        return res

    def unlink(self):
        empregados = self.employee_id
        antes = self._l10n_br_dsr_participacao(empregados)
        res = super().unlink()
        self._l10n_br_dsr_reconciliar(antes, empregados, self.browse())
        return res

    def _l10n_br_gravar_datas_falta(self, datas, faltas=None):
        """Faz as datas de falta do holerite serem exatamente ``datas``.

        ``faltas`` (a contagem) vai na mesma gravação: baixar a contagem antes
        de apagar as datas velhas faria "datas <= faltas" falhar no meio.
        """
        self.ensure_one()
        datas = set(datas)
        atuais = {f.date: f for f in self.l10n_br_falta_ids}
        comandos = [(2, f.id) for d, f in atuais.items() if d not in datas]
        comandos += [(0, 0, {"date": d}) for d in sorted(datas - set(atuais))]
        vals = {}
        if faltas is not None and faltas != self.l10n_br_faltas_injustificadas:
            vals["l10n_br_faltas_injustificadas"] = faltas
        if comandos:
            vals["l10n_br_falta_ids"] = comandos
        if vals:
            self.write(vals)

    # Códigos referenciados por regras COMPARTILHADAS entre estruturas cuja
    # regra-fonte pode não estar na estrutura corrente (ex.: a regra IRRF é
    # usada por CLT e Estatutário e referencia FALTAS/DESC_DSR, que só
    # existem na estrutura CLT). Estes garantem o default mesmo quando a regra
    # que os define está ausente da estrutura do holerite.
    _L10N_BR_BASELOCALDICT_BASELINE = (
        "FALTAS",
        "DESC_DSR",
        "INSS",
        "CONTRIB_RPPS",
        "PENSAO_ALIMENTICIA",
        "BASE_IRRF",
        "SALARIO_MATERNIDADE",
    )

    def _get_baselocaldict(self, contracts):
        """Pre-populate rule codes with 0.0 defaults (RF-15).

        Rules with conditional execution (e.g. FALTAS only when faltas > 0)
        may not fire, leaving their code absent from localdict. Uma regra que
        referencie o código "nu" de outra regra ainda-não-calculada
        levantaria ``NameError``.

        A pré-população é EXTENSÍVEL: em vez de depender só de uma tupla fixa
        mantida à mão (que já causou bugs quando uma regra satélite
        referenciava um código fora da lista), os defaults são derivados das
        PRÓPRIAS regras das estruturas do holerite - qualquer código presente
        na estrutura fica disponível desde o início do cálculo, sem manutenção.

        Mantém-se ainda uma baseline mínima
        (``_L10N_BR_BASELOCALDICT_BASELINE``) para os códigos referenciados por
        regras compartilhadas entre estruturas cuja regra-fonte pode não estar
        na estrutura corrente (a regra IRRF, usada por CLT e Estatutário,
        referencia FALTAS/DESC_DSR que só existem na CLT).
        """
        localdict = super()._get_baselocaldict(contracts)
        for code in self._L10N_BR_BASELOCALDICT_BASELINE:
            localdict.setdefault(code, 0.0)
        for rule in self._get_salary_rules():
            if rule.code:
                localdict.setdefault(rule.code, 0.0)
        return localdict

    def _get_competencia(self):
        """Data de referência (fato gerador) para resolver as tabelas fiscais.

        Convenção: fim do período do holerite (``date_to``), com fallback para
        ``date_from``. Para holerites mensais ambos caem no mesmo mês; em
        períodos que cruzam a virada de uma vigência (ex.: férias abril->maio),
        vale a tabela vigente no encerramento/pagamento.
        """
        return self.date_to or self.date_from

    # Estrutura MENSAL (fonte da média de verbas habituais, RF-18, e do
    # salário já pago): a que paga o salário (rubrica ``SALARIO_BASE``, da
    # categoria BASIC, na estrutura ou na estrutura-pai) e não tem rubrica de
    # férias, 13º ou rescisão. Vale pelas rubricas, não pelo código da
    # estrutura: ``CLT_BASIS`` e qualquer estrutura própria entram sem
    # cadastro (TG-89).
    _L10N_BR_CODIGO_SALARIO_ESTRUTURA = "SALARIO_BASE"
    _L10N_BR_CODIGOS_NAO_MENSAL = (
        "FERIAS",
        "ADIANTAMENTO_13",
        "DECIMO_TERCEIRO_BRUTO",
        "SALDO_SALARIO",
    )
    # Rubricas que pagam o SALÁRIO dos dias do mês: o salário base e, nos dias
    # de licença-maternidade, o salário-maternidade (TG-87). A rescisão e a
    # integridade com as férias contam as duas como "salário já pago".
    _L10N_BR_CODIGOS_SALARIO_MENSAL = ("SALARIO_BASE", "SALARIO_MATERNIDADE")
    # Adicionais contratuais fixos pagos no mensal (TG-88).
    _L10N_BR_CODIGOS_ADICIONAIS_FIXOS = (
        "ADICIONAL_PERICULOSIDADE",
        "ADICIONAL_INSALUBRIDADE",
    )

    @api.model
    def _l10n_br_estruturas_mensais(self):
        """Estruturas mensais: com a rubrica de salário e sem as de férias/13º/rescisão.

        Conta também as rubricas da estrutura-pai: a estrutura própria que só
        acrescenta rubricas à ``CLT`` (``parent_id``) herda o ``SALARIO_BASE``.
        """
        nao_mensal = set(self._L10N_BR_CODIGOS_NAO_MENSAL)
        mensais = self.env["hr.payroll.structure"]
        for estrutura in self.env["hr.payroll.structure"].search([]):
            codigos = set(
                estrutura.get_structure_with_parents().rule_ids.mapped("code")
            )
            if self._L10N_BR_CODIGO_SALARIO_ESTRUTURA in codigos and not (
                codigos & nao_mensal
            ):
                mensais |= estrutura
        return mensais

    def _l10n_br_eh_mensal(self):
        """``True`` se a estrutura do holerite é mensal (ver acima)."""
        self.ensure_one()
        return self.struct_id in self._l10n_br_estruturas_mensais()

    def _l10n_br_media_habitual(self, codes, janela_meses=12):
        """Média de `codes` nos holerites MENSAIS anteriores (RF-18).

        Súmula 45 TST / CLT art. 142: parcelas variáveis habituais (horas
        extras habituais, adicional noturno) integram férias, 13º e as
        verbas rescisórias pela média, não pelo valor do mês de referência.

        Lê os holerites de estrutura MENSAL (pelas rubricas) do mesmo
        contrato, já CONFIRMADOS (``state == "done"`` - este motor de folha
        não usa um estado "paid" separado), com competência anterior à deste
        holerite, dentro da janela de `janela_meses` meses (ou desde o início
        do contrato, se mais recente que a janela). Holerites de férias, 13º
        e rescisão são excluídos: não são "mês trabalhado" para este fim.

        Args:
            codes: iterável de códigos de rubrica a somar por holerite
                (ex.: ``("HE_50", "HE_100", "ADICIONAL_NOTURNO")``).
            janela_meses: tamanho da janela (padrão 12, Súmula 45 TST).

        Returns:
            Média mensal (float, 0.0 se não houver holerites na janela).
        """
        self.ensure_one()
        contract = self.contract_id
        referencia = self.date_from or self.date_to
        if not contract or not referencia:
            return 0.0
        limite = referencia - relativedelta(months=janela_meses)
        if contract.date_start and contract.date_start > limite:
            limite = contract.date_start
        payslips = self.env["hr.payslip"].search(
            [
                ("contract_id", "=", contract.id),
                ("struct_id", "in", self._l10n_br_estruturas_mensais().ids),
                ("state", "=", "done"),
                ("l10n_br_fora_de_vigor", "=", False),
                ("date_from", "<", referencia),
                ("date_from", ">=", limite),
            ],
            order="date_from",
        )
        codes = tuple(codes)
        valores = [
            sum(p.line_ids.filtered(lambda ln: ln.code in codes).mapped("total"))
            for p in payslips
        ]
        return salary_rules_br.calc_media_habitual(valores, janela_meses)

    def _l10n_br_feriados_competencia(self):
        """Feriados do mês da competência, no calendário de trabalho do contrato.

        O módulo não tem calendário de feriados próprio: usa as ausências
        GLOBAIS (``resource.calendar.leaves`` sem recurso, o "feriado" do
        Odoo) do calendário do contrato, ou sem calendário (valem para todos),
        da empresa do holerite. Cada dia coberto pela ausência, no fuso do
        calendário, é um feriado. Sem ausência cadastrada, devolve vazio e o
        repouso do mês são só os domingos.

        Critério (``salary_rules_br.dia_feriado_da_ausencia``): ausência de UM
        dia que cobre o expediente inteiro, lida no fuso do calendário do
        contrato (sem calendário: o da empresa; sem ele, UTC) e NÃO no do
        usuário que a lançou. Meio expediente e recesso de vários dias não
        são feriado.

        Returns:
            ``set`` de ``date`` dentro do mês da competência.
        """
        self.ensure_one()
        competencia = self._get_competencia()
        if not competencia:
            return set()
        inicio = competencia.replace(day=1)
        fim = inicio + relativedelta(months=1, days=-1)
        contrato = self.contract_id
        calendario = contrato.resource_calendar_id if contrato else False
        empresa = self.company_id or contrato.company_id
        fuso = pytz.timezone(
            (calendario and calendario.tz)
            or (empresa and empresa.partner_id.tz)
            or "UTC"
        )
        # Folga de dois dias nas pontas: as datas guardadas são UTC.
        limite_ini = fields.Datetime.to_datetime(inicio - relativedelta(days=2))
        limite_fim = fields.Datetime.to_datetime(fim + relativedelta(days=3))
        ausencias = (
            self.env["resource.calendar.leaves"]
            .sudo()
            .search(
                [
                    ("resource_id", "=", False),
                    ("calendar_id", "in", [False, calendario.id if calendario else 0]),
                    ("company_id", "in", [False, empresa.id]),
                    ("date_from", "<", limite_fim),
                    ("date_to", ">", limite_ini),
                ]
            )
        )

        marcacoes = (
            calendario.attendance_ids.filtered(lambda m: not m.display_type)
            if calendario
            else self.env["resource.calendar.attendance"]
        )

        def do_dia(semana):
            return marcacoes.filtered(lambda m: int(m.dayofweek) == semana)

        def cauda(semana):
            """Marcações que começam à 0h de um turno que vem da véspera."""
            anterior = do_dia((semana - 1) % 7)
            if not any(m.hour_to >= 23.99 for m in anterior):
                return marcacoes.browse()
            return do_dia(semana).filtered(lambda m: m.hour_from <= 0.01)

        def janela(dia):
            """Expediente do ``dia`` no calendário, em horas desde a 0h do dia.

            Um turno que cruza a meia-noite (22h-24h mais 0h-6h do dia
            seguinte) é um expediente só: a janela do dia vai até o fim do
            turno (24 + 6). Sem expediente no dia, o dia local inteiro.
            """
            semana = dia.weekday()
            proprias = do_dia(semana) - cauda(semana)
            if not proprias:
                return 0.0, 24.0
            fim = max(proprias.mapped("hour_to"))
            if fim >= 23.99:
                fim = 24.0 + max(cauda((semana + 1) % 7).mapped("hour_to") or [0.0])
            return min(proprias.mapped("hour_from")), fim

        def local(valor):
            return pytz.utc.localize(valor).astimezone(fuso).replace(tzinfo=None)

        feriados = set()
        for ausencia in ausencias:
            dia = salary_rules_br.dia_feriado_da_ausencia(
                local(ausencia.date_from), local(ausencia.date_to), janela
            )
            if dia and inicio <= dia <= fim:
                feriados.add(dia)
        return feriados

    def _l10n_br_dias_dsr_competencia(self):
        """``(dias úteis, dias de repouso)`` do mês da competência.

        Ponto único para o reflexo no DSR: outros módulos (ponto eletrônico)
        sobrescrevem para informar os dias da própria apuração, sem criar uma
        segunda rubrica de DSR.
        """
        self.ensure_one()
        competencia = self._get_competencia()
        return salary_rules_br.dias_dsr(
            competencia.year, competencia.month, self._l10n_br_feriados_competencia()
        )

    def _l10n_br_adicionais_fixos_vigentes(self, contract, dias=30):
        """Periculosidade e insalubridade VIGENTES no contrato, por ``dias``.

        Percentual constante do salário (30% da periculosidade; 10/20/40% do
        salário mínimo na insalubridade). Não acumulam (Súmula 364 TST), mas
        cada flag é lida de forma independente, como nas rubricas do holerite
        mensal. Cada rubrica é arredondada sozinha, como a rubrica do mensal
        (``ADICIONAL_PERICULOSIDADE`` e ``ADICIONAL_INSALUBRIDADE``): a soma
        dos valores arredondados é o que o mensal pagou (TG-130).
        """
        self.ensure_one()
        total = 0.0
        if contract.l10n_br_periculosidade:
            total += salary_rules_br.round_money(contract.wage * 0.30 * dias / 30)
        if contract.l10n_br_insalubridade:
            salario_minimo = self.env["l10n_br.hr.payroll.inss.faixa"]._salario_minimo(
                self._get_competencia()
            )
            percentuais = {"minimo": 0.10, "medio": 0.20, "maximo": 0.40}
            total += salary_rules_br.round_money(
                salario_minimo
                * percentuais.get(contract.l10n_br_grau_insalubridade, 0.10)
                * dias
                / 30
            )
        return salary_rules_br.round_money(total)

    def _l10n_br_adicionais_fixos(self, contract):
        """Periculosidade e insalubridade na remuneração-base das verbas.

        Integram a base de férias, 13º, aviso prévio e demais verbas
        rescisórias (CLT art. 142, § 5º; Súmulas 132 e 139 do TST). Valem o
        MAIOR entre o valor mensal cheio vigente no contrato e a média do
        que foi pago nos mensais confirmados dos últimos 12 meses (CLT art.
        142, § 6º): quem tem o adicional hoje recebe o valor cheio; quem o
        perdeu depois de meses pagos recebe a média, não zero (TG-130).

        O histórico é o pago nos holerites mensais confirmados
        (``_l10n_br_media_habitual``): não há histórico do indicador no
        contrato. Mês de salário parcial (admissão, afastamento) entra com o
        valor proporcional pago, como nas demais médias.
        """
        self.ensure_one()
        vigente = self._l10n_br_adicionais_fixos_vigentes(contract)
        media = self._l10n_br_media_habitual(self._L10N_BR_CODIGOS_ADICIONAIS_FIXOS)
        return max(vigente, media)

    def _l10n_br_salario_pago_mensal(self, contract, com_adicionais=False):
        """Salário já pago nos holerites MENSAIS do mesmo período (sem cancelados).

        Usado pela rescisão para não pagar de novo, no saldo de salário, os
        dias que o holerite mensal da mesma competência já pagou. Sem holerite
        mensal sobreposto, devolve 0 e a rescisão paga o saldo inteiro.
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
        codigos = self._L10N_BR_CODIGOS_SALARIO_MENSAL
        if com_adicionais:
            codigos += self._L10N_BR_CODIGOS_ADICIONAIS_FIXOS
        return sum(
            mensais.mapped("line_ids")
            .filtered(lambda ln: ln.code in codigos)
            .mapped("total")
        )

    def _l10n_br_afastamentos_inss(self, contract):
        """Afastamentos aprovados do empregado cujos dias após o 15º são do INSS.

        Traz também os que começaram antes do período, pois a contagem dos 15
        dias da empresa parte do início do afastamento.
        """
        self.ensure_one()
        if not self.date_from or not self.date_to:
            return []
        leaves = (
            self.env["hr.leave"]
            .sudo()
            .search(
                [
                    ("employee_id", "=", contract.employee_id.id),
                    ("state", "=", "validate"),
                    ("holiday_status_id.l10n_br_afastamento_inss", "=", True),
                    ("request_date_from", "<=", self.date_to),
                    ("request_date_to", ">=", self.date_from),
                ]
            )
        )
        return [(lv.request_date_from, lv.request_date_to) for lv in leaves]

    def _l10n_br_maternidade(self, contract):
        """Licenças-maternidade aprovadas do empregado que tocam o período.

        Pares ``(inicio, fim)`` dos afastamentos de tipo "Licença-maternidade".
        Fonte única dos dias de salário-maternidade: ``dias_salario`` e
        ``dias_maternidade`` leem daqui, no mesmo conjunto de dias.
        """
        self.ensure_one()
        if not self.date_from or not self.date_to:
            return []
        leaves = (
            self.env["hr.leave"]
            .sudo()
            .search(
                [
                    ("employee_id", "=", contract.employee_id.id),
                    ("state", "=", "validate"),
                    ("holiday_status_id.l10n_br_salario_maternidade", "=", True),
                    ("request_date_from", "<=", self.date_to),
                    ("request_date_to", ">=", self.date_from),
                ]
            )
        )
        return [(lv.request_date_from, lv.request_date_to) for lv in leaves]

    def _l10n_br_dias_maternidade(self, contract):
        """Dias do período pagos como salário-maternidade (mês de 30 dias).

        Do mesmo conjunto de dias de ``dias_salario``: o salário base paga
        ``dias_salario - dias_maternidade``.
        """
        self.ensure_one()
        return salary_rules_br.dias_maternidade_mes(
            self.date_from,
            self.date_to,
            contract.date_start,
            contract.date_end,
            self._l10n_br_afastamentos_inss(contract),
            self._l10n_br_ferias_gozadas(contract),
            self._l10n_br_maternidade(contract),
        )

    def _l10n_br_dias_maternidade_na_estrutura(self, contract):
        """Dias de maternidade que ESTE holerite paga na rubrica própria.

        Só vale com a rubrica ``SALARIO_MATERNIDADE`` na estrutura do holerite:
        sem ela, tirar os dias do ``SALARIO_BASE`` os faria sumir (estrutura
        montada com a mesma regra de salário, como a ``ESTATUTO`` antiga ou a
        de estágio). Sem a rubrica o salário segue inteiro no ``SALARIO_BASE``.
        """
        self.ensure_one()
        regras = self._get_salary_rules()
        if not any(r.code == "SALARIO_MATERNIDADE" for r in regras):
            return 0
        return self._l10n_br_dias_maternidade(contract)

    def _l10n_br_ferias_gozadas(self, contract):
        """Períodos ``(inicio, fim)`` de férias gozadas já pagas em recibo.

        Gancho: o recibo de férias vive no ``l10n_br_hr_vacation``, que o
        sobrescreve. Sem ele, não há férias a descontar.
        """
        return []

    def _l10n_br_semanas_com_falta(self, contract=None):
        """Repousos que este holerite desconta: semanas com falta mais as sem data."""
        self.ensure_one()
        donas, sem_data = self._l10n_br_dsr_participacao(self.employee_id).get(
            self.id, (frozenset(), 0)
        )
        return len(donas) + sem_data

    def _l10n_br_inss_ferias_competencia(self, contract):
        """``(base, retido)`` de INSS dos recibos de férias da competência.

        Gancho sobrescrito pelo ``l10n_br_hr_vacation``. Sem recibos de férias,
        ``(0.0, 0.0)`` e o INSS do mensal é apurado só sobre o próprio bruto.
        """
        return (0.0, 0.0)

    def _get_tools_dict(self):
        tools = super()._get_tools_dict()
        # `self` é único aqui (chamado a partir de _get_baselocaldict, que faz
        # ensure_one). Resolvemos a competência do holerite e vinculamos
        # funções que já carregam a tabela vigente - as regras continuam
        # chamando tools.br.calc_inss(base) sem passar o ano.
        competencia = self._get_competencia()
        inss_model = self.env["l10n_br.hr.payroll.inss.faixa"]
        irrf_model = self.env["l10n_br.hr.payroll.irrf.faixa"]
        redutor_model = self.env["l10n_br.hr.payroll.irrf.redutor"]
        sf_model = self.env["l10n_br.hr.payroll.sal.familia.faixa"]
        dep_model = self.env["l10n_br.hr.payroll.irrf.dependente"]

        def calc_inss(salario_bruto):
            return salary_rules_br.calc_inss(
                salario_bruto, inss_model._tabela(competencia)
            )

        def calc_irrf(base_irrf):
            return salary_rules_br.calc_irrf(base_irrf, irrf_model._tabela(competencia))

        def redutor_irrf(rendimento_bruto, imposto_apurado):
            """Redutor do IRPF (Lei 15.270/2025) vigente na competência."""
            return salary_rules_br.calc_redutor_irrf(
                rendimento_bruto, imposto_apurado, redutor_model._tabela(competencia)
            )

        def irrf_apos_redutor(rendimento_bruto, imposto_apurado):
            """Imposto do mês já abatido o redutor vigente na competência.

            Competências anteriores a 01/2026 não têm redutor cadastrado e o
            imposto retorna inalterado (comportamento antigo preservado).
            """
            return salary_rules_br.calc_irrf_apos_redutor(
                rendimento_bruto, imposto_apurado, redutor_model._tabela(competencia)
            )

        def irrf_mais_favoravel(rendimento_tributavel, base_legal):
            """IRRF pela forma mais favorável, com as tabelas da competência.

            Usada por TODAS as apurações (mensal, férias, 13º e rescisão):
            compara dedução legal x desconto simplificado (Lei 9.250/95,
            art. 4º, § 2º) e aplica o redutor da Lei 9.250/95, art. 3º-A,
            sobre o resultado.
            """
            return salary_rules_br.calc_irrf_mais_favoravel(
                rendimento_tributavel,
                base_legal,
                irrf_model._tabela(competencia),
                irrf_model._desconto_simplificado(competencia),
                redutor_model._tabela(competencia),
            )

        def calc_salario_familia(remuneracao, num_filhos, dias_trabalhados=30):
            return salary_rules_br.calc_salario_familia(
                remuneracao,
                num_filhos,
                sf_model._tabela(competencia),
                dias_trabalhados,
            )

        def dias_trabalhados_mes(contrato):
            """Dias de vigência do ``contrato`` no período deste holerite."""
            return salary_rules_br.dias_trabalhados_mes(
                self.date_from,
                self.date_to,
                contrato.date_start,
                contrato.date_end,
            )

        def dias_salario(contrato):
            """Dias de salário do ``contrato`` no período (mês de 30 dias).

            Considera admissão, desligamento, afastamentos previdenciários
            (tipo com ``l10n_br_afastamento_inss``: dias além do 15º são do
            INSS) e férias gozadas já pagas no recibo de férias.
            """
            return salary_rules_br.dias_salario_mes(
                self.date_from,
                self.date_to,
                contrato.date_start,
                contrato.date_end,
                self._l10n_br_afastamentos_inss(contrato),
                self._l10n_br_ferias_gozadas(contrato),
            )

        def inss_ferias_competencia(contrato):
            """``(base, retido)`` de INSS nos recibos de férias da competência."""
            return self._l10n_br_inss_ferias_competencia(contrato)

        def salario_pago_mensal(contrato, com_adicionais=False):
            """Salário já pago em holerite mensal que se sobrepõe a este período."""
            return self._l10n_br_salario_pago_mensal(contrato, com_adicionais)

        def semanas_com_falta(contrato):
            """Semanas com falta injustificada: repousos a descontar (DSR)."""
            return self._l10n_br_semanas_com_falta(contrato)

        def dias_dsr():
            return self._l10n_br_dias_dsr_competencia()

        def dsr_reflexo(valor):
            """Reflexo de ``valor`` (horas extras, adicional noturno) no DSR."""
            uteis, repouso = dias_dsr()
            return salary_rules_br.calc_dsr_reflexo(valor, uteis, repouso)

        def aliquotas_patronais(contrato, decimo_terceiro=False):
            """Alíquotas dos encargos patronais do contrato na competência.

            O RAT e o FAP são os do estabelecimento do contrato (CNPJ do
            Endereço de Trabalho do empregado) vigentes na competência; sem
            linha, valem os da empresa.

            Resolve o regime tributário da empresa DO HOLERITE (não da empresa
            do usuário: em base multiempresa o mesmo salário custa valores
            diferentes por regime, que é justamente o que se quer mostrar), o
            anexo do Simples da atividade do contrato e a transição da CPRB.

            Uso nas regras salariais::

                aliq = tools.br.aliquotas_patronais(contract)
                result = tools.br.round_money(base * aliq.cpp)

            Returns:
                ``SimpleNamespace`` com ``cpp``, ``rat``, ``terceiros``,
                ``fgts``, ``total_patronal`` e ``total_com_fgts`` (frações).
            """
            company = self.company_id or contrato.company_id
            empregado = contrato.employee_id
            return types.SimpleNamespace(
                **company._l10n_br_hr_aliquotas_patronais(
                    competencia,
                    simples_anexo=contrato.l10n_br_hr_simples_anexo,
                    aprendiz=empregado.l10n_br_tipo_contrato == "aprendiz",
                    decimo_terceiro=decimo_terceiro,
                    # RAT/FAP do estabelecimento: o mesmo local de trabalho
                    # (CNPJ do Endereço de Trabalho) que o S-2200 declara.
                    estabelecimento=empregado.address_id.vat,
                )
            )

        def media_habitual(codes, janela_meses=12):
            """Média das verbas variáveis habituais `codes` (RF-18, Súmula
            45 TST / CLT art. 142), lida dos holerites mensais anteriores."""
            return self._l10n_br_media_habitual(codes, janela_meses)

        tools["br"] = types.SimpleNamespace(
            round_money=salary_rules_br.round_money,
            calc_inss=calc_inss,
            calc_irrf=calc_irrf,
            # Redutor do IRPF da Lei 15.270/2025 (só a partir de 01/2026).
            redutor_irrf=redutor_irrf,
            irrf_apos_redutor=irrf_apos_redutor,
            # Apuração completa do IRRF (legal x simplificado + redutor).
            irrf_mais_favoravel=irrf_mais_favoravel,
            calc_ferias_dias=salary_rules_br.calc_ferias_dias,
            calc_decimo_avos=salary_rules_br.calc_decimo_avos,
            calc_vt=salary_rules_br.calc_vt,
            calc_salario_familia=calc_salario_familia,
            # Dias de vigência do contrato no mês (verbas proporcionais).
            dias_trabalhados_mes=dias_trabalhados_mes,
            # Dias de salário do mês (admissão, desligamento, afastamento).
            dias_salario=dias_salario,
            # Dias de licença-maternidade (empresa paga; rubrica própria).
            dias_maternidade=self._l10n_br_dias_maternidade_na_estrutura,
            inss_ferias_competencia=inss_ferias_competencia,
            # Salário já pago no mensal do período (compensação na rescisão).
            salario_pago_mensal=salario_pago_mensal,
            # Adicionais fixos na remuneração-base das verbas (TG-88).
            adicionais_fixos=self._l10n_br_adicionais_fixos,
            # Os mesmos adicionais pelos dias do mês, rubrica a rubrica, para
            # compensar o que o mensal pagou sem resíduo (TG-130).
            adicionais_fixos_dias=lambda contrato, dias: (
                self._l10n_br_adicionais_fixos_vigentes(contrato, dias)
            ),
            calc_pensao_alimenticia=salary_rules_br.calc_pensao_alimenticia,
            # Dias úteis/DSR da competência (RF-26).
            dias_dsr=dias_dsr,
            # Reflexo no DSR de horas extras e adicional noturno (TG-86).
            dsr_reflexo=dsr_reflexo,
            # Repousos perdidos por falta: um por semana com falta (TG-84).
            semanas_com_falta=semanas_com_falta,
            # Encargos patronais por regime tributário (RF-31/32/33).
            aliquotas_patronais=aliquotas_patronais,
            # Provisões de férias/13º por competência (RF-34).
            calc_provisao_ferias=salary_rules_br.calc_provisao_ferias,
            calc_provisao_decimo_terceiro=(
                salary_rules_br.calc_provisao_decimo_terceiro
            ),
            calc_encargos_sobre_provisao=(salary_rules_br.calc_encargos_sobre_provisao),
            # Média de verbas variáveis habituais (RF-18).
            media_habitual=media_habitual,
            # Aviso prévio proporcional (Lei 12.506/2011) e meses de contrato
            # (estimativa de saldo do FGTS quando não informado) - RF-06.
            aviso_previo_dias=salary_rules_br.calc_aviso_previo_dias,
            meses_trabalhados=salary_rules_br.calc_meses_trabalhados,
            # Resolvidos por competência (lazy: só falham se a regra usar).
            irrf_deducao_dependente=lambda: dep_model._valor(competencia),
            desconto_simplificado=lambda: irrf_model._desconto_simplificado(
                competencia
            ),
            salario_minimo=lambda: inss_model._salario_minimo(competencia),
            teto_inss=lambda: inss_model._teto(competencia),
        )
        return tools

    @api.model
    def _demo_compute_payslips(self):
        """Compute all draft demo payslips. Called from demo XML via <function>.

        Varre TODAS as empresas: a demo de regime tributário (RF-35) cria
        holerites em empresas diferentes da principal, e a regra multiempresa
        do Odoo filtra o ``search`` pelas empresas permitidas no contexto - sem
        ampliar ``allowed_company_ids`` os holerites das outras empresas
        ficariam em rascunho e sem linhas. Cada holerite é calculado com a
        própria empresa como empresa ativa, para que nada dependa da empresa
        do usuário que rodou a demo.
        """
        todas = self.env["res.company"].sudo().search([])
        payslips = self.with_context(allowed_company_ids=todas.ids).search(
            [("state", "=", "draft")]
        )
        for slip in payslips:
            try:
                slip.with_company(slip.company_id).compute_sheet()
            except Exception:
                _logger.warning(
                    "Demo: falha ao calcular holerite %s", slip.name, exc_info=True
                )
        _logger.info("Demo: %d holerites calculados", len(payslips))
