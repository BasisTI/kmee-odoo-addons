# Copyright 2024 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import models

from . import vale_transporte


class HrPayslip(models.Model):
    _inherit = "hr.payslip"

    def _get_baselocaldict(self, contracts):
        localdict = super()._get_baselocaldict(contracts)
        for code in ("DESC_VT", "DESC_PLANO_SAUDE", "VT_INFO"):
            localdict.setdefault(code, 0.0)
        return localdict

    def _l10n_br_vt_dias_semana(self, contract):
        """Dias da semana (0 = segunda) em que a escala do empregado trabalha."""
        calendario = (
            contract.resource_calendar_id
            or contract.employee_id.resource_calendar_id
            or contract.company_id.resource_calendar_id
        )
        marcacoes = calendario.attendance_ids.filtered(lambda m: not m.display_type)
        if not marcacoes:
            return {0, 1, 2, 3, 4}
        return {int(m.dayofweek) for m in marcacoes}

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
            self._l10n_br_vt_dias_semana(contract),
            self._l10n_br_feriados_competencia(),
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
