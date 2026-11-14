# Copyright 2024 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from datetime import timedelta

import pytz

from odoo import fields, models

from . import vale_transporte


class HrPayslip(models.Model):
    _inherit = "hr.payslip"

    def _get_baselocaldict(self, contracts):
        localdict = super()._get_baselocaldict(contracts)
        for code in ("DESC_VT", "DESC_PLANO_SAUDE", "VT_INFO"):
            localdict.setdefault(code, 0.0)
        return localdict

    def _l10n_br_vt_trabalha(self, contract):
        """``f(date) -> bool``: o empregado trabalha no dia pela escala do contrato.

        Respeita o calendário quinzenal (12x36): cada marcação vale só na
        semana do seu tipo. Sem marcações, segunda a sexta.
        """
        calendario = (
            contract.resource_calendar_id
            or contract.employee_id.resource_calendar_id
            or contract.company_id.resource_calendar_id
        )
        marcacoes = calendario.attendance_ids.filtered(lambda m: not m.display_type)
        if not marcacoes:
            return lambda dia: dia.weekday() < 5
        quinzenal = calendario.two_weeks_calendar
        marcacao = self.env["resource.calendar.attendance"]
        escala = {}
        for m in marcacoes:
            tipo = int(m.week_type) if quinzenal and m.week_type else None
            escala.setdefault(int(m.dayofweek), set()).add(tipo)

        def trabalha(dia):
            tipos = escala.get(dia.weekday())
            if not tipos:
                return False
            return None in tipos or marcacao.get_week_type(dia) in tipos

        return trabalha

    def _l10n_br_vt_recessos(self, contract):
        """Dias do período cobertos por inteiro por ausência global (recesso).

        Complementa os feriados de um dia só do DSR: a ausência global de dois
        dias ou mais (recesso coletivo) também tira o deslocamento.
        """
        self.ensure_one()
        calendario = contract.resource_calendar_id
        empresa = self.company_id or contract.company_id
        fuso = pytz.timezone(
            (calendario and calendario.tz)
            or (empresa and empresa.partner_id.tz)
            or "UTC"
        )
        limite_ini = fields.Datetime.to_datetime(self.date_from - timedelta(days=2))
        limite_fim = fields.Datetime.to_datetime(self.date_to + timedelta(days=3))
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

        def local(valor):
            return pytz.utc.localize(valor).astimezone(fuso).replace(tzinfo=None)

        return vale_transporte.dias_cobertos(
            self.date_from,
            self.date_to,
            [(local(a.date_from), local(a.date_to)) for a in ausencias],
        )

    def _l10n_br_vt_feriados_publicos(self, contract):
        """Feriados do ``l10n_br_hr_holidays_public`` no período, se instalado.

        Sem dependência dura: lê ``calendar.public.holiday.line`` só se o
        modelo existir. Vale o feriado sem estado/município ou o do estado/
        município do empregado (endereço de trabalho; sem ele, o da empresa).
        """
        self.ensure_one()
        linhas = self.env.get("calendar.public.holiday.line")
        if linhas is None:
            return set()
        parceiro = (
            contract.employee_id.address_id
            or (self.company_id or contract.company_id).partner_id
        )
        dominio = [("date", ">=", self.date_from), ("date", "<=", self.date_to)]
        achadas = linhas.sudo().search(dominio)
        if "state_ids" in linhas._fields:
            achadas = achadas.filtered(
                lambda ln: not ln.state_ids or parceiro.state_id in ln.state_ids
            )
        if "city_ids" in linhas._fields:
            achadas = achadas.filtered(
                lambda ln: not ln.city_ids or parceiro.city_id in ln.city_ids
            )
        return set(achadas.mapped("date"))

    def _l10n_br_vt_ausencias(self, contract):
        """Pares ``(inicio, fim)`` de dias inteiros sem deslocamento no período.

        Afastamentos, licenças e férias aprovados do empregado. Ausência por
        hora ou de meio dia não tira o deslocamento do dia.
        """
        self.ensure_one()
        leaves = (
            self.env["hr.leave"]
            .sudo()
            .search(
                [
                    ("employee_id", "=", contract.employee_id.id),
                    ("state", "=", "validate"),
                    ("request_date_from", "<=", self.date_to),
                    ("request_date_to", ">=", self.date_from),
                ]
            )
            .filtered(lambda lv: not lv.request_unit_half and not lv.request_unit_hours)
        )
        pares = [(lv.request_date_from, lv.request_date_to) for lv in leaves]
        return pares + list(self._l10n_br_ferias_gozadas(contract))

    def _l10n_br_vt_dias_uteis(self, contract):
        """Dias úteis do mês em que o empregado recebe VT.

        Escala do contrato, menos feriados do calendário e afastamentos ou
        férias do mês; admissão e desligamento no meio do mês contam só os dias
        de vigência do contrato.
        """
        self.ensure_one()
        inicio = self.date_from
        fim = self.date_to
        if contract.date_start and contract.date_start > inicio:
            inicio = contract.date_start
        if contract.date_end and contract.date_end < fim:
            fim = contract.date_end
        return vale_transporte.dias_uteis_vt(
            inicio,
            fim,
            self._l10n_br_vt_trabalha(contract),
            self._l10n_br_feriados_competencia()
            | self._l10n_br_vt_recessos(contract)
            | self._l10n_br_vt_feriados_publicos(contract),
            self._l10n_br_vt_ausencias(contract),
        )

    def _l10n_br_vt_credito(self, contract):
        """Crédito do VT do mês.

        Com ``VT_DIARIO`` no contrato: valor diário da tarifa x dias úteis. Sem
        ele, o ``VT`` mensal fixo (cadastro antigo).
        """
        self.ensure_one()
        advantages = contract.advantages_ids
        diario = sum(
            advantages.filtered(
                lambda a: a.advantage_template_code == "VT_DIARIO"
            ).mapped("amount")
        )
        if diario > 0:
            return vale_transporte.credito_vt(
                diario, self._l10n_br_vt_dias_uteis(contract)
            )
        return sum(
            advantages.filtered(lambda a: a.advantage_template_code == "VT").mapped(
                "amount"
            )
        )

    def _get_tools_dict(self):
        tools = super()._get_tools_dict()

        def credito_vt(contrato):
            return self._l10n_br_vt_credito(contrato)

        def dias_uteis_vt(contrato):
            return self._l10n_br_vt_dias_uteis(contrato)

        tools["br"].credito_vt = credito_vt
        tools["br"].dias_uteis_vt = dias_uteis_vt
        return tools
