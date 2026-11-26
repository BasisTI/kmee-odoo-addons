# Copyright 2024 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

from .res_company import SIMPLES_ANEXO


class HrContract(models.Model):
    _inherit = "hr.contract"

    l10n_br_hr_simples_anexo = fields.Selection(
        selection=SIMPLES_ANEXO,
        string="Anexo do Simples (Atividade)",
        help="Anexo do Simples Nacional da atividade exercida pelo empregado, "
        "quando diferente do anexo preponderante da empresa. Vazio = usa o "
        "anexo da empresa.\n\n"
        "Serve à atividade concomitante do Simples: uma optante com atividade "
        "do anexo IV (construção civil, vigilância, limpeza) recolhe a "
        "contribuição patronal por fora do DAS (LC 123/2006, art. 18, §5º-C) "
        "para os empregados dessa atividade, ainda que o anexo preponderante "
        "seja outro. É eixo INDEPENDENTE da desoneração/CPRB.",
    )
    l10n_br_hora_noturna_reduzida = fields.Boolean(
        string="Hora Noturna Reduzida",
        default=True,
        help="Marcado: o trabalho noturno conta pela hora de 52min30s (CLT, "
        "art. 73, § 1º) e o holerite converte as horas noturnas (x 8/7). "
        "Desmarque para quem não tem esse direito, como o trabalhador rural "
        "(Lei 5.889/73, art. 7º: hora de 60 min, adicional de 25%, noturno das "
        "21h às 5h na lavoura e das 20h às 4h na pecuária) ou quem tem "
        "convenção coletiva que afaste a redução. Para o rural, ajuste também o "
        "Percentual do Adicional Noturno. O módulo não identifica o rural nem "
        "aplica o horário noturno rural: as horas noturnas vêm informadas (ou "
        "da apuração, que usa 22h às 5h). Súmula 60 do TST (prorrogação após as "
        "5h) não é tratada. A mudança vale para holerites novos e em rascunho; "
        "holerite confirmado ou pago não muda.",
    )
    l10n_br_adicional_noturno_perc = fields.Float(
        string="Percentual do Adicional Noturno",
        default=20.0,
        help="Percentual do adicional noturno sobre o salário-hora: 20% na CLT "
        "urbana (art. 73), 25% para o trabalhador rural (Lei 5.889/73, art. 7º). "
        "Maior que 0 e até 100. Só a regra salarial padrão lê este campo: regra "
        "personalizada do adicional noturno usa a própria fórmula e o ignora.",
    )
    l10n_br_is_horista = fields.Boolean(
        string="Horista",
        compute="_compute_l10n_br_is_horista",
        help="Marcado quando a Unidade do Salário (campo ``salary_unit`` do "
        "l10n_br_hr_contract, undSalFixo do eSocial) é Hourly (código 1). Serve "
        "às views e aos relatórios.",
    )
    l10n_br_valor_hora = fields.Monetary(
        string="Valor da Hora",
        currency_field="currency_id",
        help="Valor da hora do horista: contrato com a Unidade do Salário "
        "Hourly (código 1). Nessa unidade o Salário do contrato passa a ser o "
        "mensal de referência (valor da hora × horas do mês do contrato), só "
        "leitura; o holerite paga as horas trabalhadas e o repouso semanal "
        "remunerado pela regra DSR_HORISTA (Lei 605/49, art. 7º, b). "
        "Vale-transporte, periculosidade, VA/VR e as demais regras que leem o "
        "Salário usam o mensal de referência. É a fonte do salário, das horas "
        "extras, do adicional noturno e do repouso do horista, e do vrSalFx do "
        "eSocial (undSalFixo 1). Vazio para o mensalista.\n\n"
        "Unidades Monthly (5), Não aplicável (7) ou sem unidade: salário "
        "mensal. Daily, Weekly, Biweekly e Task ainda não são calculadas: o "
        "holerite é recusado.\n\n"
        "Férias, 13º e rescisão do horista usam a média das horas pagas no "
        "período (mais o repouso) pelo valor da hora vigente, não o mensal de "
        "referência.",
    )
    wage = fields.Monetary(
        compute="_compute_wage_horista",
        store=True,
        readonly=False,
    )
    l10n_br_periculosidade = fields.Boolean(
        string="Periculosidade",
        help="Adicional de periculosidade (30% do salário base)",
    )
    l10n_br_insalubridade = fields.Boolean(
        string="Insalubridade",
    )
    l10n_br_grau_insalubridade = fields.Selection(
        selection=[
            ("minimo", "Mínimo (10%)"),
            ("medio", "Médio (20%)"),
            ("maximo", "Máximo (40%)"),
        ],
        string="Grau de Insalubridade",
    )

    # Códigos do ``salary_unit`` (undSalFixo do eSocial, tabela 14).
    _L10N_BR_UNIDADE_HORA = "1"
    _L10N_BR_UNIDADE_MES = "5"
    # Unidades suportadas: Hourly (1), Monthly (5) e contrato sem unidade (= mensal).
    # As demais (2 Daily, 3 Weekly, 4 Biweekly, 6 Task, 7 Não aplicável) são
    # recusadas no holerite e no eSocial: calculá-las como mês pagaria valor
    # errado, e o eSocial exige dscSalVar (6 e 7) e vrSalFx 0 (7).
    _L10N_BR_UNIDADES_SUPORTADAS = {"1", "5"}

    def _l10n_br_codigo_unidade(self):
        """Código do ``salary_unit``; sem unidade (banco antigo): mensal."""
        self.ensure_one()
        return self.salary_unit.code or self._L10N_BR_UNIDADE_MES

    def _l10n_br_horista(self):
        """``True`` se o salário do contrato é por hora (valor da hora)."""
        self.ensure_one()
        return self._l10n_br_codigo_unidade() == self._L10N_BR_UNIDADE_HORA

    @api.depends("salary_unit", "salary_unit.code")
    def _compute_l10n_br_is_horista(self):
        for rec in self:
            rec.l10n_br_is_horista = rec.salary_unit.code == rec._L10N_BR_UNIDADE_HORA

    def _l10n_br_unidade_suportada(self):
        self.ensure_one()
        return self._l10n_br_codigo_unidade() in self._L10N_BR_UNIDADES_SUPORTADAS

    def _l10n_br_exigir_unidade_suportada(self):
        """``UserError`` se algum contrato tem unidade do salário não suportada."""
        invalidos = self.filtered(lambda c: not c._l10n_br_unidade_suportada())
        if invalidos:
            raise UserError(
                _(
                    "A Unidade do Salário só pode ser Hourly (horista) ou Monthly "
                    "(mensal) por enquanto; diária, semanal, quinzenal, por "
                    "tarefa e não aplicável ainda não são suportadas. Corrija "
                    "o contrato: %(contratos)s.",
                    contratos=", ".join(
                        "%s (%s)" % (c.display_name, c.employee_id.name or "-")
                        for c in invalidos
                    ),
                )
            )

    def _l10n_br_und_sal_fixo(self):
        """``undSalFixo`` do eSocial: o código do ``salary_unit`` (1 ou 5)."""
        self.ensure_one()
        self._l10n_br_exigir_unidade_suportada()
        return int(self._l10n_br_codigo_unidade())

    def _l10n_br_unidade_do_vals(self, vals):
        """``True``/``False`` se ``vals`` põe/tira a unidade Hora; ``None`` se
        ``vals`` não mexe na unidade."""
        if "salary_unit" not in vals:
            return None
        unidade = self.env["hr.contract.salary.unit"].browse(vals["salary_unit"] or [])
        return unidade.code == self._L10N_BR_UNIDADE_HORA

    def _l10n_br_salario_hora(self):
        """Salário-hora: o próprio salário do horista; senão salário ÷ divisor."""
        self.ensure_one()
        if self._l10n_br_horista():
            return self.l10n_br_valor_hora
        return self.wage / self._l10n_br_divisor_horas_mensais()

    def _l10n_br_vr_sal_fixo(self):
        """``vrSalFx`` do eSocial: valor da hora (horista) ou salário mensal."""
        self.ensure_one()
        if self._l10n_br_horista():
            return self.l10n_br_valor_hora
        return self.wage

    # Divisor mensal padrão CLT (44h semanais × 5): usado como fallback
    # quando o contrato não tem calendário de trabalho configurado.
    _L10N_BR_DIVISOR_PADRAO = 220.0

    def _l10n_br_horas_semanais(self):
        """Horas contratuais semanais derivadas do calendário de trabalho.

        Soma a jornada das linhas de presença (``attendance_ids``) de uma
        semana, sem as linhas de intervalo (``day_period = lunch``, que o Odoo
        traz no calendário padrão, como ``12:00-13:00``) nem as seções do
        calendário de duas semanas. Em calendários de duas semanas
        (``two_weeks_calendar``) a soma é dividida por 2 para obter a média
        semanal.

        Returns:
            Horas semanais (float); ``0.0`` se não houver calendário/jornada.
        """
        self.ensure_one()
        calendar = self.resource_calendar_id
        if not calendar or not calendar.attendance_ids:
            return 0.0
        attendances = calendar.attendance_ids.filtered(
            lambda a: not a.display_type and a.day_period != "lunch"
        )
        total = sum(a.hour_to - a.hour_from for a in attendances)
        if calendar.two_weeks_calendar:
            total /= 2.0
        return total

    def _l10n_br_divisor_horas_mensais(self):
        """Divisor mensal de horas para cálculo do salário-hora (RF-26).

        Deriva da jornada do contrato: ``horas_semanais × 5`` (equivale a
        ``horas_semanais / 6 × 30`` da CLT — 44h → 220, 40h → 200). Quando o
        contrato não tem calendário/jornada, usa o divisor padrão de 220.
        """
        self.ensure_one()
        horas_semanais = self._l10n_br_horas_semanais()
        if not horas_semanais:
            return self._L10N_BR_DIVISOR_PADRAO
        return horas_semanais * 5.0

    @api.depends(
        "salary_unit",
        "salary_unit.code",
        "l10n_br_valor_hora",
        "resource_calendar_id",
        "resource_calendar_id.attendance_ids",
        "resource_calendar_id.attendance_ids.hour_from",
        "resource_calendar_id.attendance_ids.hour_to",
        "resource_calendar_id.two_weeks_calendar",
    )
    def _compute_wage_horista(self):
        """Horista: o Salário é o mensal de referência (valor-hora × divisor).

        Para o mensalista o valor digitado fica como está.
        """
        for rec in self:
            if rec._l10n_br_horista() and rec.l10n_br_valor_hora > 0:
                rec.wage = round(
                    rec.l10n_br_valor_hora * rec._l10n_br_divisor_horas_mensais(), 2
                )
            else:
                # Mensalista, ou Hourly ainda sem valor da hora: o ``wage``
                # gravado fica (nunca zera o mensal em silêncio).
                rec.wage = rec.wage

    @api.model_create_multi
    def create(self, vals_list):
        # O mensal do horista é calculado: o ``wage`` informado é ignorado.
        for vals in vals_list:
            if self._l10n_br_unidade_do_vals(vals):
                vals["wage"] = 0.0
        records = super().create(vals_list)
        for rec in records.filtered(lambda c: c._l10n_br_horista()):
            rec._l10n_br_atualiza_wage_horista()
        return records

    def _l10n_br_atualiza_wage_horista(self):
        self.ensure_one()
        mensal = round(
            self.l10n_br_valor_hora * self._l10n_br_divisor_horas_mensais(), 2
        )
        if self.wage != mensal:
            return super(HrContract, self).write({"wage": mensal})
        return True

    def _l10n_br_vals_sem_wage_do_horista(self, vals):
        """``vals`` sem o ``wage`` quando o contrato é (ou vira) horista.

        O mensal do horista é calculado do Valor da Hora: o ``wage`` gravado à
        mão é ignorado. Horista ainda sem Valor da Hora (banco antigo, TG-168)
        não tem de onde calcular: o ``wage`` digitado é gravado, como o do
        mensalista. Em lote misto, o ``wage`` dos demais contratos é gravado aqui.
        """
        if "wage" not in vals:
            return vals
        vira_hora = self._l10n_br_unidade_do_vals(vals)
        if vira_hora is None:
            horistas = self.filtered(lambda c: c._l10n_br_horista())
        else:
            horistas = self if vira_hora else self.browse()
        if "l10n_br_valor_hora" in vals:
            com_valor = vals["l10n_br_valor_hora"] > 0
            horistas = horistas if com_valor else self.browse()
        else:
            horistas = horistas.filtered(lambda c: c.l10n_br_valor_hora > 0)
        if not horistas:
            return vals
        resto = self - horistas
        if resto:
            resto.write({"wage": vals["wage"]})
        return {k: v for k, v in vals.items() if k != "wage"}

    @api.constrains("salary_unit", "l10n_br_valor_hora")
    def _check_valor_hora_horista(self):
        for rec in self:
            if rec._l10n_br_horista() and rec.l10n_br_valor_hora <= 0:
                raise ValidationError(
                    _("Informe o Valor da Hora (maior que zero) do contrato horista.")
                )

    @api.constrains("l10n_br_periculosidade", "l10n_br_insalubridade")
    def _check_periculosidade_insalubridade(self):
        """Periculosidade e insalubridade não acumulam (Súmula 364 TST)."""
        for rec in self:
            if rec.l10n_br_periculosidade and rec.l10n_br_insalubridade:
                raise ValidationError(
                    _(
                        "Não é permitido acumular periculosidade e insalubridade "
                        "(Súmula 364 do TST)."
                    )
                )

    @api.constrains("l10n_br_adicional_noturno_perc")
    def _check_adicional_noturno_perc(self):
        """O percentual do adicional noturno é maior que 0 e até 100."""
        for rec in self:
            if not 0 < rec.l10n_br_adicional_noturno_perc <= 100:
                raise ValidationError(
                    _(
                        "O percentual do adicional noturno deve ser maior que 0 e "
                        "no máximo 100 (informado: %(perc).2f).",
                        perc=rec.l10n_br_adicional_noturno_perc,
                    )
                )

    def write(self, vals):
        if self._l10n_br_unidade_do_vals(vals) is False and (
            "l10n_br_valor_hora" not in vals
        ):
            # Saiu de Hourly: o valor da hora velho não pode voltar a valer
            # quando o contrato retornar a Hourly (TG-168).
            vals = dict(vals, l10n_br_valor_hora=0.0)
        res = super().write(self._l10n_br_vals_sem_wage_do_horista(vals))
        if "l10n_br_hora_noturna_reduzida" in vals:
            # Só holerite em rascunho acompanha: o confirmado guarda o que valeu.
            # ``sudo``: o gerente de contratos pode não ter acesso à folha, e a
            # busca é só dos rascunhos deste contrato.
            self.env["hr.payslip"].sudo().search(
                [
                    ("contract_id", "in", self.ids),
                    ("state", "in", ("draft", "verify")),
                ]
            ).write(
                {"l10n_br_usar_hora_reduzida": vals["l10n_br_hora_noturna_reduzida"]}
            )
        return res
