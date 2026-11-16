# Copyright 2026 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from datetime import timedelta

from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

ANOS_PRESCRICAO = 5  # CF art. 7º, XXIX; CLT art. 149 conta do fim do concessivo


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
        "XXIX). Só avisa; não bloqueia.",
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

    def _l10n_br_periodo_da_ausencia(self):
        """Período aquisitivo que esta ausência debita, em dias corridos, ou um
        recordset vazio."""
        self.ensure_one()
        if not self._l10n_br_ferias_ativa():
            return self.env["hr.leave.allocation"]
        return self.env["hr.leave.allocation"]._l10n_br_periodo_debitado(
            self.employee_id,
            self.request_date_from,
            antes=(self.request_date_from, self.id or 0),
        )

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
            dias, limite = leave._l10n_br_dias_dobro()
            leave.l10n_br_aviso_dobro = (
                _(
                    "Atenção RH: %(dias)s dia(s) depois do fim do período concessivo "
                    "(%(limite)s). Esses dias são pagos em dobro, com o terço "
                    "(CLT art. 137).",
                    dias=dias,
                    limite=fields.Date.to_string(limite),
                )
                if dias
                else False
            )
            prescrito = bool(
                limite
                and leave.request_date_from
                > limite + relativedelta(years=ANOS_PRESCRICAO)
            )
            leave.l10n_br_aviso_prescricao = (
                _(
                    "Atenção RH: o concessivo deste período terminou em %(limite)s, "
                    "há mais de %(anos)s anos: a pretensão às férias pode estar "
                    "prescrita (CLT art. 149; CF art. 7º, XXIX). Confirme com o "
                    "jurídico antes de pagar.",
                    limite=fields.Date.to_string(limite),
                    anos=ANOS_PRESCRICAO,
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
        """Férias não passam dos dias de direito, contados em dias corridos.

        O ``hr_holidays`` conta dias úteis no tipo Férias; o direito (CLT art.
        130) e o abono são em dias corridos.
        """
        Allocation = self.env["hr.leave.allocation"]
        ativas = self.filtered(
            lambda lv: lv.state in ("confirm", "validate1", "validate")
            and lv._l10n_br_ferias_ativa()
        )
        for employee in ativas.employee_id:
            alocacoes = Allocation._l10n_br_alocacoes_ferias(employee)
            if not alocacoes:
                continue
            ausencias = Allocation._l10n_br_ausencias_ferias(employee)
            excesso = Allocation._l10n_br_distribuir(alocacoes, ausencias)[2]
            if any(excesso.values()):
                raise ValidationError(
                    _(
                        "%(nome)s não tem dias de férias para cobrir essa ausência: "
                        "o período aquisitivo cobre o direito (CLT art. 130), "
                        "descontado o abono pecuniário, em dias corridos.",
                        nome=employee.name,
                    )
                )

    @api.model_create_multi
    def create(self, vals_list):
        leaves = super().create(vals_list)
        for leave in leaves:
            for aviso in (leave.l10n_br_aviso_dobro, leave.l10n_br_aviso_prescricao):
                if aviso:
                    leave.message_post(body=aviso, subtype_xmlid="mail.mt_note")
        return leaves
