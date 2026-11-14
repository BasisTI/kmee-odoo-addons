# Copyright 2024 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""Dados do recibo e do aviso de férias, calculados fora do QWeb.

O recibo reaproveita a classificação do contracheque (``report_holerite``) e
não recalcula nada: salário, média e adicionais vêm do que o cálculo gravou no
holerite (``l10n_br_ferias_*``). O aviso é o comunicado do art. 135 da CLT e
parte da ausência de férias aprovada (``hr.leave``): é nela que o RH registra o
período, antes de o holerite existir.
"""
from datetime import timedelta

import pytz

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from odoo.addons.l10n_br_hr_payroll.models import salary_rules_br

# CLT art. 135: a concessão é comunicada ao empregado com, no mínimo, 30 dias.
DIAS_ANTECEDENCIA_AVISO = 30
# CLT art. 145: o pagamento é feito até 2 dias antes do início do período.
DIAS_ANTECEDENCIA_PAGAMENTO = 2
# Sem calendário no contrato, segunda a sexta.
SEMANA_UTIL_PADRAO = {0, 1, 2, 3, 4}


class ReportReciboFerias(models.AbstractModel):
    _name = "report.l10n_br_hr_payroll_report.report_recibo_ferias"
    _description = "Dados do recibo de férias"

    @api.model
    def _get_report_values(self, docids, data=None):
        docs = self.env["hr.payslip"].browse(docids)
        holerite = self.env["report.l10n_br_hr_payroll_report.report_holerite"]
        return {
            "doc_ids": docids,
            "doc_model": "hr.payslip",
            "docs": docs,
            "contracheque": {slip.id: holerite.contracheque(slip) for slip in docs},
            "ferias": {slip.id: self.dados_ferias(slip) for slip in docs},
        }

    @api.model
    def periodo_gozo(self, slip):
        """``(início, fim)`` do gozo do recibo, ou ``(False, False)`` sem gozo.

        Mesma regra da folha mensal (``_l10n_br_ferias_gozadas``): o gozo começa
        em ``date_from`` e dura os dias gozados, sem passar de ``date_to``.
        Os dias de abono não são gozados e não entram. Holerite só de abono
        (0 dias gozados) não tem período de gozo.
        """
        dias = slip.l10n_br_dias_ferias_gozadas
        if dias <= 0:
            return False, False
        inicio = slip.date_from
        return inicio, min(slip.date_to, inicio + timedelta(days=dias - 1))

    @api.model
    def _feriados(self, calendario, empresa, inicio, fim):
        """Feriados entre ``inicio`` e ``fim``: ausências globais de um dia
        do calendário (mesmo critério do DSR) e os feriados públicos, se o
        módulo ``l10n_br_hr_holidays_public`` estiver instalado."""
        fuso = pytz.timezone(
            (calendario and calendario.tz)
            or (empresa and empresa.partner_id.tz)
            or "UTC"
        )
        ausencias = (
            self.env["resource.calendar.leaves"]
            .sudo()
            .search(
                [
                    ("resource_id", "=", False),
                    ("calendar_id", "in", [False, calendario.id if calendario else 0]),
                    ("company_id", "in", [False, empresa.id if empresa else 0]),
                    (
                        "date_from",
                        "<",
                        fields.Datetime.to_datetime(fim + timedelta(days=3)),
                    ),
                    (
                        "date_to",
                        ">",
                        fields.Datetime.to_datetime(inicio - timedelta(days=2)),
                    ),
                ]
            )
        )
        feriados = set()
        for ausencia in ausencias:
            ini = pytz.utc.localize(ausencia.date_from).astimezone(fuso)
            term = pytz.utc.localize(ausencia.date_to).astimezone(fuso)
            dia = salary_rules_br.dia_feriado_da_ausencia(
                ini.replace(tzinfo=None), term.replace(tzinfo=None)
            )
            if dia:
                feriados.add(dia)
        publicos = self.env.get("calendar.public.holiday.line")
        if publicos is not None:
            feriados |= set(
                publicos.sudo()
                .search([("date", ">=", inicio), ("date", "<=", fim)])
                .mapped("date")
            )
        return feriados

    @api.model
    def retorno_ao_trabalho(self, fim_gozo, contrato, empresa=None):
        """Próximo dia de trabalho depois do gozo, no calendário do contrato.

        Pula os dias sem expediente na escala e os feriados (como a folha faz
        no DSR e no vale-transporte). Sem calendário, segunda a sexta.
        """
        calendario = contrato.resource_calendar_id if contrato else False
        marcacoes = (
            calendario.attendance_ids.filtered(lambda m: not m.display_type)
            if calendario
            else []
        )
        dias_semana = {int(m.dayofweek) for m in marcacoes} or SEMANA_UTIL_PADRAO
        empresa = empresa or (contrato.company_id if contrato else False)
        feriados = self._feriados(
            calendario, empresa, fim_gozo, fim_gozo + timedelta(days=30)
        )
        dia = fim_gozo + timedelta(days=1)
        for _i in range(30):
            if dia.weekday() in dias_semana and dia not in feriados:
                return dia
            dia += timedelta(days=1)
        return fim_gozo + timedelta(days=1)

    @api.model
    def _remuneracao(self, slip, linhas):
        """Componentes da remuneração de referência, como foram pagos.

        Lê o que o cálculo gravou. Holerite calculado antes dos campos existirem
        não os tem: o total sai das linhas (rubrica ÷ dias x 30) e as parcelas
        ficam em branco, em vez de inventadas a partir do contrato de hoje.
        """
        if slip.l10n_br_ferias_salario:
            salario = slip.l10n_br_ferias_salario
            media = slip.l10n_br_ferias_media
            adicionais = slip.l10n_br_ferias_adicionais
            return salario, media, adicionais, salario + media + adicionais
        if slip.l10n_br_dias_ferias_gozadas > 0 and linhas.get("FERIAS"):
            total = linhas["FERIAS"] * 30 / slip.l10n_br_dias_ferias_gozadas
        elif slip.l10n_br_dias_ferias_vendidas > 0 and linhas.get("ABONO_PECUNIARIO"):
            total = linhas["ABONO_PECUNIARIO"] * 30 / slip.l10n_br_dias_ferias_vendidas
        else:
            total = 0.0
        return None, None, None, round(total, 2)

    @api.model
    def dados_ferias(self, slip):
        """Período, abono, composição da remuneração e prazo de pagamento."""
        slip.ensure_one()
        alocacao = slip.l10n_br_ferias_allocation_id
        inicio, fim = self.periodo_gozo(slip)
        linhas = {ln.code: ln.total for ln in slip.line_ids}
        salario, media, adicionais, remuneracao = self._remuneracao(slip, linhas)
        fracao, fracoes = self._fracao(slip)
        return {
            "cancelado": slip.state == "cancel",
            "aquisitivo_inicio": alocacao.date_from if alocacao else False,
            "aquisitivo_fim": alocacao.date_to if alocacao else False,
            "dias_direito": alocacao.number_of_days if alocacao else 0,
            "gozo_inicio": inicio,
            "gozo_fim": fim,
            "dias_gozados": (fim - inicio).days + 1 if inicio else 0,
            "retorno": self.retorno_ao_trabalho(fim, slip.contract_id, slip.company_id)
            if fim
            else False,
            "pagar_ate": inicio - timedelta(days=DIAS_ANTECEDENCIA_PAGAMENTO)
            if inicio
            else False,
            "dias_abono": slip.l10n_br_dias_ferias_vendidas,
            "valor_abono": linhas.get("ABONO_PECUNIARIO", 0.0),
            "terco_abono": linhas.get("ADICIONAL_ABONO", 0.0),
            "valor_ferias": linhas.get("FERIAS", 0.0),
            "terco_ferias": linhas.get("ADICIONAL_FERIAS", 0.0),
            "salario": salario,
            "media": media,
            "adicionais": adicionais,
            "remuneracao": remuneracao,
            "valor_dia": round(remuneracao / 30, 2),
            "fracao": fracao,
            "fracoes": fracoes,
        }

    @api.model
    def _fracao(self, slip):
        """``(número, total)`` da fração, ou ``(0, 0)`` sem alocação ou cancelada.

        A posição conta todos os holerites da alocação, inclusive os cancelados:
        cancelar o do meio não renumera os outros. O total é a maior posição de
        um holerite válido. Cancelado não é fração de ninguém.
        """
        alocacao = slip.l10n_br_ferias_allocation_id
        if not alocacao or slip.state == "cancel" or slip.l10n_br_fora_de_vigor:
            return 0, 0
        todos = (
            self.env["hr.payslip"]
            .search(
                [
                    ("l10n_br_ferias_allocation_id", "=", alocacao.id),
                    ("l10n_br_dias_periodo_gozado", ">", 0),
                ]
            )
            .sorted(lambda p: (p.date_from, p.id))
        )
        validos = [
            i + 1
            for i, p in enumerate(todos)
            if p.state != "cancel" and not p.l10n_br_fora_de_vigor
        ]
        if slip.id not in todos.ids:
            return 1, 1
        return todos.ids.index(slip.id) + 1, max(validos)


class ReportAvisoFerias(models.AbstractModel):
    _name = "report.l10n_br_hr_payroll_report.report_aviso_ferias"
    _description = "Dados do aviso de férias"

    @api.model
    def _get_report_values(self, docids, data=None):
        docs = self.env["hr.leave"].browse(docids)
        return {
            "doc_ids": docids,
            "doc_model": "hr.leave",
            "docs": docs,
            "aviso": {leave.id: self.dados_aviso(leave) for leave in docs},
        }

    @api.model
    def _verificar_ausencia(self, leave):
        tipo = self.env.ref("l10n_br_hr_vacation.leave_type_ferias")
        if leave.holiday_status_id != tipo:
            raise UserError(
                _("O aviso de férias só se emite para ausência do tipo Férias.")
            )
        if leave.state != "validate":
            raise UserError(
                _("O aviso de férias só se emite para ausência de férias aprovada.")
            )

    @api.model
    def _recibos_da_ausencia(self, leave):
        """Holerites de férias (não cancelados) que cobrem o período da ausência."""
        return self.env["hr.payslip"].search(
            [
                ("employee_id", "=", leave.employee_id.id),
                ("struct_id.code", "=", "FERIAS"),
                ("state", "!=", "cancel"),
                ("l10n_br_fora_de_vigor", "=", False),
                ("date_from", "<=", leave.request_date_to),
                ("date_to", ">=", leave.request_date_from),
            ],
            order="date_from, id",
        )

    @api.model
    def dados_aviso(self, leave, data_emissao=None):
        """Período, retorno, abono e prazo do aviso de uma ausência de férias.

        A data de emissão é gravada na ausência na primeira emissão e não muda
        nas reimpressões, que por isso não acusam atraso que não houve. Emitir
        com menos de 30 dias de antecedência não é bloqueado: o aviso sai com
        alerta (art. 135 da CLT).
        """
        leave.ensure_one()
        self._verificar_ausencia(leave)
        inicio, fim = leave.request_date_from, leave.request_date_to
        empregado = leave.employee_id
        contrato = empregado.contract_id
        recibos = self._recibos_da_ausencia(leave)
        recibo = recibos[:1]
        alocacao = recibo.l10n_br_ferias_allocation_id
        modelo_recibo = self.env[
            "report.l10n_br_hr_payroll_report.report_recibo_ferias"
        ]
        fracao, fracoes = modelo_recibo._fracao(recibo) if recibo else (0, 0)
        emissao = leave.l10n_br_aviso_ferias_data
        if not emissao:
            emissao = data_emissao or fields.Date.context_today(leave)
            leave.sudo().with_context(tracking_disable=True).write(
                {"l10n_br_aviso_ferias_data": emissao}
            )
        antecedencia = (inicio - emissao).days
        return {
            "inicio": inicio,
            "fim": fim,
            "dias": (fim - inicio).days + 1,
            "retorno": modelo_recibo.retorno_ao_trabalho(
                fim, contrato, leave.employee_id.company_id
            ),
            "dias_abono": sum(recibos.mapped("l10n_br_dias_ferias_vendidas")),
            "aquisitivo_inicio": alocacao.date_from if alocacao else False,
            "aquisitivo_fim": alocacao.date_to if alocacao else False,
            "fracao": fracao,
            "fracoes": fracoes,
            "pagar_ate": inicio - timedelta(days=DIAS_ANTECEDENCIA_PAGAMENTO),
            "emissao": emissao,
            "data_minima": inicio - timedelta(days=DIAS_ANTECEDENCIA_AVISO),
            "antecedencia": antecedencia,
            "fora_do_prazo": antecedencia < DIAS_ANTECEDENCIA_AVISO,
            "dias_antecedencia_minima": DIAS_ANTECEDENCIA_AVISO,
        }
