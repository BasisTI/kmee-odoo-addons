# Copyright 2024 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

# Estados em que o holerite já foi confirmado: o valor gravado não se recalcula.
ESTADOS_CONFIRMADOS = ("done", "paid")
# Estados em que o holerite ainda é um rascunho: acompanha a CCT.
ESTADOS_ABERTOS = ("draft", "verify")


class L10nBrHrCollectiveConvention(models.Model):
    _name = "l10n.br.hr.collective.convention"
    _description = "Convenção Coletiva de Trabalho"
    _order = "date_start desc"

    name = fields.Char(required=True)
    partner_union_id = fields.Many2one(
        comodel_name="res.partner",
        string="Sindicato",
        domain=[("union_entity_code", "!=", False)],
        required=True,
    )
    date_start = fields.Date(
        string="Vigência Início",
        required=True,
    )
    date_end = fields.Date(
        string="Vigência Fim",
        required=True,
    )
    dissidio_month = fields.Selection(
        selection=[
            ("1", "Janeiro"),
            ("2", "Fevereiro"),
            ("3", "Março"),
            ("4", "Abril"),
            ("5", "Maio"),
            ("6", "Junho"),
            ("7", "Julho"),
            ("8", "Agosto"),
            ("9", "Setembro"),
            ("10", "Outubro"),
            ("11", "Novembro"),
            ("12", "Dezembro"),
        ],
        string="Mês do Dissídio (Data-Base)",
    )
    wage_floor = fields.Float(
        string="Piso Salarial",
        digits="Payroll",
        help="Piso salarial definido pela convenção coletiva.",
    )
    wage_floor_job_ids = fields.One2many(
        comodel_name="l10n.br.hr.convention.wage.floor",
        inverse_name="convention_id",
        string="Pisos por Cargo",
    )
    contribution_employee_pct = fields.Float(
        string="Contribuição Empregado (%)",
        help="Percentual de contribuição assistencial do empregado.",
    )
    contribution_employer_pct = fields.Float(
        string="Contribuição Patronal (%)",
        help="Percentual de contribuição patronal ao sindicato.",
    )
    assistencial_amount = fields.Float(
        string="Contribuição Assistencial (R$)",
        digits="Payroll",
        help="Valor da contribuição assistencial previsto na CCT. O módulo só "
        "informa o valor: quem paga (autorização, direito de oposição, "
        "experiência) é decidido pela regra salarial que o lê.",
    )
    assistencial_sindicalizado = fields.Selection(
        selection=[
            ("full", "Integral"),
            ("half", "Metade"),
            ("zero", "Isento"),
        ],
        string="Assistencial do Sindicalizado",
        default="full",
        required=True,
        help="Quanto da contribuição assistencial a CCT cobra de quem é "
        "sindicalizado: integral, metade ou nada.",
    )
    assistencial_exempt_trial = fields.Boolean(
        string="Isenta Contrato de Experiência",
        help="A CCT isenta da contribuição assistencial quem está em contrato "
        "de experiência.",
    )
    monthly_fee_amount = fields.Float(
        string="Mensalidade Sindical (R$)",
        digits="Payroll",
        help="Valor da mensalidade sindical do sindicalizado previsto na CCT.",
    )
    dsr_days_per_week = fields.Integer(
        string="Dias de DSR por Semana com Falta",
        default=1,
        help="Dias de repouso descontados por semana com falta, conforme a CCT.",
    )
    vt_employee_pct = fields.Float(
        string="Vale-Transporte do Empregado (%)",
        help="Percentual do salário do mês que a CCT permite descontar do "
        "empregado a título de vale-transporte (6 = 6%).",
    )
    vavr_range_ids = fields.One2many(
        comodel_name="l10n.br.hr.convention.vavr.range",
        inverse_name="convention_id",
        string="Desconto de VA/VR por Faixa",
    )
    active = fields.Boolean(default=True)
    notes = fields.Text(string="Observações")

    _CCT_CAMPOS_VIGILIADOS = (
        "partner_union_id",
        "date_start",
        "date_end",
        "active",
        "wage_floor",
        "wage_floor_job_ids",
        "contribution_employee_pct",
        "contribution_employer_pct",
        "assistencial_amount",
        "assistencial_sindicalizado",
        "assistencial_exempt_trial",
        "monthly_fee_amount",
        "dsr_days_per_week",
        "vt_employee_pct",
        "vavr_range_ids",
    )

    @api.constrains("date_start", "date_end", "partner_union_id", "active")
    def _check_vigencia(self):
        """Vigência coerente e sem sobreposição no mesmo sindicato.

        Duas CCT ativas do mesmo sindicato que cobrem o mesmo dia deixariam a
        "vigente na competência" ambígua.
        """
        for rec in self:
            if rec.date_end < rec.date_start:
                raise ValidationError(
                    _("A vigência da CCT termina antes de começar: %s.", rec.name)
                )
            if not rec.active:
                continue
            outra = self.with_context(active_test=False).search(
                [
                    ("id", "!=", rec.id),
                    ("active", "=", True),
                    ("partner_union_id", "=", rec.partner_union_id.id),
                    ("date_start", "<=", rec.date_end),
                    ("date_end", ">=", rec.date_start),
                ],
                limit=1,
            )
            if outra:
                raise ValidationError(
                    _(
                        "A vigência de %(a)s se sobrepõe à de %(b)s, do mesmo "
                        "sindicato.",
                        a=rec.name,
                        b=outra.name,
                    )
                )

    @api.constrains("wage_floor_job_ids")
    def _check_piso_cargo_unico(self):
        for rec in self:
            cargos = rec.wage_floor_job_ids.job_id
            if len(cargos) != len(rec.wage_floor_job_ids):
                raise ValidationError(
                    _("A CCT %s tem dois pisos para o mesmo cargo.", rec.name)
                )

    # ------------------------------------------------------------------
    # Leitura pelas regras salariais
    # ------------------------------------------------------------------
    def assistencial_fator_sindicalizado(self):
        """Fração da contribuição assistencial paga por quem é sindicalizado."""
        self.ensure_one()
        return {"full": 1.0, "half": 0.5, "zero": 0.0}[self.assistencial_sindicalizado]

    def vavr_rate(self, wage):
        """Taxa (fração) de desconto de VA/VR da faixa do salário, ou ``None``.

        A faixa vale até o teto informado (inclusive); a primeira que cobre o
        salário vale. ``None`` quando a CCT não tem faixa que o cubra.
        """
        self.ensure_one()
        for faixa in self.vavr_range_ids.sorted("wage_ceiling"):
            if wage <= faixa.wage_ceiling:
                return faixa.rate_pct / 100.0
        return None

    def wage_floor_for(self, job=None):
        """Piso salarial da CCT para o cargo; o piso geral sem piso do cargo."""
        self.ensure_one()
        if job:
            piso = self.wage_floor_job_ids.filtered(lambda f: f.job_id == job)[:1]
            if piso:
                return piso.wage_floor
        return self.wage_floor

    # ------------------------------------------------------------------
    # Integridade com os holerites (valor que muda o cálculo)
    # ------------------------------------------------------------------
    def _cct_snapshot(self):
        """O que a CCT entrega às regras, por id; muda se algo que calcula mudar."""
        res = {}
        for rec in self:
            valores = [
                rec._fields[nome].convert_to_write(rec[nome], rec)
                for nome in self._CCT_CAMPOS_VIGILIADOS
                if nome not in ("wage_floor_job_ids", "vavr_range_ids")
            ]
            pisos = sorted((f.job_id.id, f.wage_floor) for f in rec.wage_floor_job_ids)
            faixas = sorted((f.wage_ceiling, f.rate_pct) for f in rec.vavr_range_ids)
            res[rec.id] = (tuple(map(str, valores)), tuple(pisos), tuple(faixas))
        return res

    def _cct_holerites(self):
        """Holerites que leem esta CCT na competência (sem cancelados e estornos)."""
        slips = self.env["hr.payslip"]
        for rec in self.filtered("id"):
            candidatos = (
                self.env["hr.payslip"]
                .sudo()
                .search(
                    [
                        ("state", "!=", "cancel"),
                        ("l10n_br_fora_de_vigor", "=", False),
                        ("date_to", ">=", rec.date_start),
                        ("date_to", "<=", rec.date_end),
                        (
                            "contract_id.l10n_br_cct_id.partner_union_id",
                            "=",
                            rec.partner_union_id.id,
                        ),
                    ]
                )
            )
            slips |= candidatos.filtered(
                lambda s, rec=rec: s.contract_id._l10n_br_cct_vigente(s.date_to) == rec
            )
        return slips

    @api.model
    def _cct_aplicar_aos_holerites(self, holerites):
        """Recusa se algum holerite afetado está confirmado; recalcula os abertos."""
        holerites = holerites.sudo()
        confirmados = holerites.filtered(lambda s: s.state in ESTADOS_CONFIRMADOS)
        if confirmados:
            raise UserError(
                _(
                    "A mudança altera o cálculo de holerite já confirmado: "
                    "%s. Volte-os para rascunho antes.",
                    ", ".join(confirmados.mapped("display_name")),
                )
            )
        abertos = holerites.filtered(lambda s: s.state in ESTADOS_ABERTOS)
        if abertos:
            abertos.compute_sheet()

    def _cct_guardar(self, operacao):
        """Executa ``operacao(registros)`` (grava/apaga) e propaga aos holerites.

        Compara a CCT antes e depois: se o que as regras leem mudou, os holerites
        em rascunho/verificação são recalculados na mesma transação e a gravação
        é recusada se algum estiver confirmado. Gravações aninhadas (as linhas de
        piso e de faixa, dentro da gravação da CCT) não repetem a conferência.
        """
        if self.env.context.get("l10n_br_cct_guardando"):
            return operacao(self)
        contexto = self.with_context(l10n_br_cct_guardando=True)
        antes = self._cct_snapshot()
        slips = self._cct_holerites()
        res = operacao(contexto)
        existentes = self.exists()
        mudou = len(existentes) != len(self) or any(
            antes[i] != v for i, v in existentes._cct_snapshot().items()
        )
        if mudou:
            self._cct_aplicar_aos_holerites(slips | existentes._cct_holerites())
        return res

    @api.model_create_multi
    def create(self, vals_list):
        recs = super(
            L10nBrHrCollectiveConvention,
            self.with_context(l10n_br_cct_guardando=True),
        ).create(vals_list)
        recs = recs.with_env(self.env)
        if not self.env.context.get("l10n_br_cct_guardando"):
            self._cct_aplicar_aos_holerites(recs._cct_holerites())
        return recs

    def write(self, vals):
        if not set(vals) & set(self._CCT_CAMPOS_VIGILIADOS):
            return super().write(vals)
        return self._cct_guardar(
            lambda recs: super(L10nBrHrCollectiveConvention, recs).write(vals)
        )

    def unlink(self):
        return self._cct_guardar(
            lambda recs: super(L10nBrHrCollectiveConvention, recs).unlink()
        )

    @api.depends("partner_union_id", "date_start")
    def _compute_display_name(self):
        for rec in self:
            if rec.partner_union_id and rec.date_start:
                rec.display_name = (
                    f"{rec.partner_union_id.name} - "
                    f"{rec.date_start.year}/{rec.date_start.year + 1}"
                )
            else:
                rec.display_name = rec.name


class L10nBrHrConventionLineMixin(models.AbstractModel):
    """Linhas da CCT (pisos, faixas): gravá-las passa pela conferência da CCT."""

    _name = "l10n.br.hr.convention.line.mixin"
    _description = "Linha da CCT com conferência dos holerites"

    @api.model_create_multi
    def create(self, vals_list):
        convencoes = self.env["l10n.br.hr.collective.convention"].browse(
            [v["convention_id"] for v in vals_list if v.get("convention_id")]
        )
        return convencoes._cct_guardar(
            lambda c: super(L10nBrHrConventionLineMixin, self.with_env(c.env)).create(
                vals_list
            )
        )

    def write(self, vals):
        return self.convention_id._cct_guardar(
            lambda c: super(L10nBrHrConventionLineMixin, self.with_env(c.env)).write(
                vals
            )
        )

    def unlink(self):
        return self.convention_id._cct_guardar(
            lambda c: super(L10nBrHrConventionLineMixin, self.with_env(c.env)).unlink()
        )


class L10nBrHrConventionWageFloor(models.Model):
    _name = "l10n.br.hr.convention.wage.floor"
    _inherit = ["l10n.br.hr.convention.line.mixin"]
    _description = "Piso Salarial por Cargo"

    convention_id = fields.Many2one(
        comodel_name="l10n.br.hr.collective.convention",
        required=True,
        ondelete="cascade",
    )
    job_id = fields.Many2one(
        comodel_name="hr.job",
        string="Cargo",
        required=True,
    )
    wage_floor = fields.Float(
        string="Piso Salarial",
        digits="Payroll",
        required=True,
    )


class L10nBrHrConventionVavrRange(models.Model):
    _name = "l10n.br.hr.convention.vavr.range"
    _inherit = ["l10n.br.hr.convention.line.mixin"]
    _description = "Faixa de Desconto de VA/VR da CCT"
    _order = "convention_id, wage_ceiling"

    convention_id = fields.Many2one(
        comodel_name="l10n.br.hr.collective.convention",
        required=True,
        ondelete="cascade",
    )
    wage_ceiling = fields.Float(
        string="Salário até",
        digits="Payroll",
        required=True,
        help="Teto da faixa (inclusive): vale para o salário até este valor.",
    )
    rate_pct = fields.Float(
        string="Desconto (%)",
        required=True,
        help="Percentual do VA/VR descontado do empregado nesta faixa.",
    )
