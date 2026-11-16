# Copyright 2026 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from datetime import timedelta

from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

from .hr_leave_allocation import L10N_BR_ANOS_PRESCRICAO


class HrLeave(models.Model):
    _inherit = "hr.leave"

    l10n_br_aviso_dobro = fields.Char(
        string="Aviso de Férias em Dobro",
        compute="_compute_l10n_br_avisos",
        help="Férias concedidas depois do período concessivo (CLT art. 134) são "
        "pagas em dobro, com o terço (CLT art. 137); nos dias que cruzam o fim do "
        "concessivo, só os dias depois dele (Súmula 81 do TST). Conta os dias do "
        "período que a ausência debita, em dias corridos.",
    )
    l10n_br_aviso_prescricao = fields.Char(
        string="Aviso de Prescrição das Férias",
        compute="_compute_l10n_br_avisos",
        help="Período cujo concessivo terminou há mais de cinco anos: a pretensão "
        "do empregado às férias pode estar prescrita (CLT art. 149; CF art. 7º, "
        "XXIX). O sistema não lança férias de período prescrito (a ausência é "
        "recusada, ver ``_check_validity``); este aviso só aparece para o que "
        "ainda caiba no horizonte.",
    )

    l10n_br_aviso_notificado = fields.Text(
        string="Último Aviso Registrado",
        copy=False,
        readonly=True,
        help="Texto do último aviso de dobra, excesso ou prescrição já registrado "
        "como nota: uma nota nova só sai quando o aviso muda.",
    )

    def _l10n_br_ferias_ativa(self):
        vacation_type = self.env.ref(
            "l10n_br_hr_vacation.leave_type_ferias", raise_if_not_found=False
        )
        return bool(
            vacation_type
            and self.holiday_status_id == vacation_type
            and self.employee_id
            and self.request_date_from
            and self.request_date_to
        )

    def _l10n_br_analise_ausencia(self):
        """``(período debitado, dias em excesso, saldo antes)`` desta ausência,
        da mesma análise que a restrição de saldo usa (período fixado pelo
        recibo incluído)."""
        self.ensure_one()
        vazio = (self.env["hr.leave.allocation"], 0, 0)
        if not self._l10n_br_ferias_ativa():
            return vazio
        Allocation = self.env["hr.leave.allocation"]
        origem = self._origin.id or self.id
        if origem and self.state in ("confirm", "validate1", "validate"):
            analise = Allocation._l10n_br_analise(
                self.employee_id,
                extra=[(origem, self.request_date_from, self.request_date_to)],
                excluir=[origem],
            )
            return analise.get(origem, vazio)
        analise = Allocation._l10n_br_analise(
            self.employee_id,
            extra=[(-1, self.request_date_from, self.request_date_to)],
            excluir=[origem] if origem else [],
        )
        return analise.get(-1, vazio)

    def _l10n_br_recibo_pode_mudar_periodo(self, alloc):
        """Nenhum recibo fixa o débito e outro período completo tem saldo."""
        self.ensure_one()
        Allocation = self.env["hr.leave.allocation"]
        if Allocation._l10n_br_periodo_do_recibo(
            self.employee_id, [self.request_date_from]
        ):
            return False
        return Allocation._l10n_br_outro_periodo_com_saldo(
            self.employee_id,
            alloc,
            self.request_date_from,
            excluir=[self._origin.id or self.id]
            if (self._origin.id or self.id)
            else [],
        )

    def _l10n_br_periodo_da_ausencia(self):
        """Período aquisitivo que esta ausência debita, em dias corridos, ou um
        recordset vazio."""
        return self._l10n_br_analise_ausencia()[0]

    def _l10n_br_dias_dobro(self):
        """Dias corridos da ausência depois do concessivo do período debitado.

        Returns:
            tuple[int, date | None]: dias em dobro e o fim do concessivo.
        """
        self.ensure_one()
        alloc = self._l10n_br_periodo_da_ausencia()
        if not alloc:
            return 0, None
        limite = alloc._l10n_br_fim_concessivo()
        depois = max(self.request_date_from, limite + timedelta(days=1))
        return max((self.request_date_to - depois).days + 1, 0), limite

    @api.depends(
        "holiday_status_id", "employee_id", "request_date_from", "request_date_to"
    )
    def _compute_l10n_br_avisos(self):
        for leave in self:
            alloc, excesso, _saldo = leave._l10n_br_analise_ausencia()
            dias, limite = leave._l10n_br_dias_dobro()
            partes = []
            if dias:
                partes.append(
                    _(
                        "Atenção RH: %(dias)s dia(s) depois do fim do período "
                        "concessivo (%(limite)s) do período aquisitivo de "
                        "%(inicio)s a %(fim)s. Esses dias são pagos em dobro, "
                        "com o terço (CLT art. 137).",
                        dias=dias,
                        limite=fields.Date.to_string(limite),
                        inicio=fields.Date.to_string(alloc.date_from),
                        fim=fields.Date.to_string(alloc.date_to),
                    )
                )
                if leave._l10n_br_recibo_pode_mudar_periodo(alloc):
                    partes.append(
                        _(
                            "Um recibo de férias de outro período, com início no "
                            "mesmo dia, fixa o débito nesse período e muda este "
                            "aviso."
                        )
                    )
            if alloc and excesso:
                partes.append(
                    _(
                        "Atenção RH: a ausência passa %(excesso)s dia(s) do saldo "
                        "do período aquisitivo de %(inicio)s a %(fim)s. Ela já "
                        "está lançada; confira o débito e ajuste ou lance o "
                        "resto noutra ausência.",
                        excesso=int(excesso),
                        inicio=fields.Date.to_string(alloc.date_from),
                        fim=fields.Date.to_string(alloc.date_to),
                    )
                )
            leave.l10n_br_aviso_dobro = " ".join(partes) or False
            prescrito = bool(
                limite
                and leave.request_date_from
                > limite + relativedelta(years=L10N_BR_ANOS_PRESCRICAO)
            )
            leave.l10n_br_aviso_prescricao = (
                _(
                    "Atenção RH: o concessivo deste período terminou em %(limite)s, "
                    "há mais de %(anos)s anos: a pretensão às férias pode estar "
                    "prescrita (CLT art. 149; CF art. 7º, XXIX). Confirme com o "
                    "jurídico antes de pagar.",
                    limite=fields.Date.to_string(limite),
                    anos=L10N_BR_ANOS_PRESCRICAO,
                )
                if prescrito
                else False
            )

    @api.onchange(
        "holiday_status_id", "employee_id", "request_date_from", "request_date_to"
    )
    def _onchange_l10n_br_aviso_dobro(self):
        self._compute_l10n_br_avisos()
        mensagens = [
            m for m in (self.l10n_br_aviso_dobro, self.l10n_br_aviso_prescricao) if m
        ]
        if mensagens:
            return {
                "warning": {
                    "title": _("Férias em dobro"),
                    "message": "\n".join(mensagens),
                }
            }

    @api.constrains(
        "holiday_status_id",
        "employee_id",
        "request_date_from",
        "request_date_to",
        "state",
    )
    def _check_l10n_br_dias_corridos(self):
        """A ausência cabe no saldo do período que debita, em dias corridos.

        O ``hr_holidays`` conta dias úteis no tipo Férias; o direito (CLT art.
        130) e o abono são em dias corridos. Uma ausência debita um único
        período, de aquisitivo completo (CLT art. 134): o que passa do saldo
        dele é recusado, sem transbordar. Só vale para o período debitado pelas
        ausências criadas ou alteradas: o dado legado acima do direito em outro
        período não barra a ausência. Férias coletivas (CLT art. 140) ficam
        fora deste limite.
        """
        Allocation = self.env["hr.leave.allocation"]
        ativas = self.filtered(
            lambda lv: lv.state in ("confirm", "validate1", "validate")
            and lv._l10n_br_ferias_ativa()
        )
        for employee in ativas.employee_id:
            analise = Allocation._l10n_br_analise(employee)
            destino = {c: v[0] for c, v in analise.items()}
            excesso = {c: v[1] for c, v in analise.items()}
            saldo = {c: v[2] for c, v in analise.items()}
            minhas = ativas.filtered(lambda lv: lv.employee_id == employee)
            periodos = {destino[lv.id] for lv in minhas if destino.get(lv.id)}
            for lv in minhas:
                if excesso.get(lv.id):
                    self._l10n_br_recusar_excesso(
                        lv, destino[lv.id], saldo[lv.id], excesso[lv.id]
                    )
            # ausência já lançada, empurrada para fora do saldo por esta (fora de
            # ordem): recusa quem a empurrou
            for chave, alloc in destino.items():
                if alloc in periodos and excesso.get(chave):
                    self._l10n_br_recusar_excesso(
                        self.browse(chave), alloc, saldo[chave], excesso[chave]
                    )

    def _check_validity(self):
        """Ausência de férias depois do horizonte (concessivo mais 5 anos, a
        prescrição do art. 149) é recusada com mensagem clara, antes da do
        ``hr_holidays``."""
        Allocation = self.env["hr.leave.allocation"]
        for leave in self.filtered(lambda lv: lv._l10n_br_ferias_ativa()):
            completos = Allocation._l10n_br_alocacoes_ferias(
                leave.employee_id
            ).filtered(lambda a: a.date_to < leave.request_date_from)
            if completos and all(
                a._l10n_br_horizonte() < leave.request_date_from for a in completos
            ):
                raise ValidationError(self._l10n_br_msg_prescricao(leave))
            if leave.state in ("confirm", "validate1", "validate"):
                alloc = leave._l10n_br_periodo_da_ausencia()
                if alloc and leave.request_date_to > alloc._l10n_br_horizonte():
                    raise ValidationError(
                        _(
                            "A ausência passa do horizonte do período aquisitivo de "
                            "%(inicio)s a %(fim)s (%(horizonte)s, cinco anos depois "
                            "do concessivo, CLT art. 149): termine a ausência até "
                            "essa data e lance o resto noutro período.",
                            inicio=fields.Date.to_string(alloc.date_from),
                            fim=fields.Date.to_string(alloc.date_to),
                            horizonte=fields.Date.to_string(alloc._l10n_br_horizonte()),
                        )
                    )
        return super()._check_validity()

    def _l10n_br_msg_prescricao(self, leave):
        return _(
            "%(nome)s: o concessivo de todos os períodos aquisitivos completos "
            "terminou há mais de %(anos)s anos da data da ausência (%(data)s): os "
            "períodos estão prescritos (CLT art. 149; CF art. 7º, XXIX) e o "
            "sistema não lança férias desses períodos. Concessão por liberalidade "
            "deve ser tratada com o jurídico.",
            nome=leave.employee_id.name,
            anos=L10N_BR_ANOS_PRESCRICAO,
            data=fields.Date.to_string(leave.request_date_from),
        )

    def _l10n_br_recusar_excesso(self, leave, alloc, saldo, excesso):
        if alloc:
            raise ValidationError(
                _(
                    "O período aquisitivo de %(inicio)s a %(fim)s tem %(saldo)s "
                    "dia(s) de saldo de férias e a ausência passa %(excesso)s dia(s) "
                    "disso. Uma ausência debita um só período: reduza-a ao saldo e "
                    "lance outra ausência para o resto.",
                    inicio=fields.Date.to_string(alloc.date_from),
                    fim=fields.Date.to_string(alloc.date_to),
                    saldo=int(saldo),
                    excesso=int(excesso),
                )
            )
        completos = (
            self.env["hr.leave.allocation"]
            ._l10n_br_alocacoes_ferias(leave.employee_id)
            .filtered(lambda a: a.date_to < leave.request_date_from)
        )
        if completos and all(
            a._l10n_br_horizonte() < leave.request_date_from for a in completos
        ):
            raise ValidationError(self._l10n_br_msg_prescricao(leave))
        raise ValidationError(
            _(
                "%(nome)s não tem período aquisitivo completo com saldo de férias "
                "para essa ausência (CLT art. 134): férias só se gozam depois de "
                "completo o período aquisitivo, e o direito (CLT art. 130) é em "
                "dias corridos, descontado o abono pecuniário.",
                nome=leave.employee_id.name,
            )
        )

    def _l10n_br_avisos_texto(self):
        self.ensure_one()
        return " ".join(
            m for m in (self.l10n_br_aviso_dobro, self.l10n_br_aviso_prescricao) if m
        )

    def _l10n_br_atualizar_notas(self, employees):
        """Reconfere os avisos das ausências de férias ativas dos empregados e
        registra uma nota nova quando o aviso mudou (por exemplo, ao recusar ou
        cancelar uma ausência anterior, que redistribui o débito das seguintes)."""
        Allocation = self.env["hr.leave.allocation"]
        for employee in employees:
            ids = [t[0] for t in Allocation._l10n_br_ausencias_ferias(employee)]
            leaves = self.sudo().browse(ids)
            leaves.invalidate_recordset(
                ["l10n_br_aviso_dobro", "l10n_br_aviso_prescricao"]
            )
            for leave in leaves:
                texto = leave._l10n_br_avisos_texto()
                if texto == (leave.l10n_br_aviso_notificado or ""):
                    continue
                if texto:
                    leave.message_post(body=texto, subtype_xmlid="mail.mt_note")
                else:
                    leave.message_post(
                        body=_(
                            "O aviso anterior desta ausência não vale mais: o "
                            "período debitado mudou."
                        ),
                        subtype_xmlid="mail.mt_note",
                    )
                leave.l10n_br_aviso_notificado = texto

    def write(self, vals):
        res = super().write(vals)
        if {
            "state",
            "request_date_from",
            "request_date_to",
            "holiday_status_id",
            "employee_id",
        } & set(vals):
            self._l10n_br_atualizar_notas(self.employee_id)
        return res

    def unlink(self):
        employees = self.employee_id
        res = super().unlink()
        self.browse()._l10n_br_atualizar_notas(employees)
        return res

    @api.model_create_multi
    def create(self, vals_list):
        leaves = super().create(vals_list)
        leaves._l10n_br_atualizar_notas(leaves.employee_id)
        return leaves
