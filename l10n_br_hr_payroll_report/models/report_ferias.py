# Copyright 2024 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""Dados do recibo e do aviso de férias, calculados fora do QWeb.

O recibo reaproveita a classificação do contracheque (``report_holerite``):
proventos, descontos, bases e líquido saem da mesma função, e o que é próprio
das férias (período aquisitivo e de gozo, abono, composição da remuneração)
vem daqui. O aviso é o comunicado do art. 135 da CLT: por escrito, com o
período de gozo e a ciência do empregado, com 30 dias de antecedência.
"""
from datetime import timedelta

from odoo import api, fields, models

# CLT art. 135: a concessão é comunicada ao empregado com, no mínimo, 30 dias.
DIAS_ANTECEDENCIA_AVISO = 30
# CLT art. 145: o pagamento é feito até 2 dias antes do início do período.
DIAS_ANTECEDENCIA_PAGAMENTO = 2


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
        """``(início, fim)`` do gozo do recibo; o fim respeita o ``date_to``.

        Mesma regra da folha mensal (``_l10n_br_ferias_gozadas``): o gozo começa
        em ``date_from`` e dura os dias gozados, sem passar de ``date_to``.
        Os dias de abono não são gozados e não entram.
        """
        dias = max(slip.l10n_br_dias_ferias_gozadas, 1)
        inicio = slip.date_from
        return inicio, min(slip.date_to, inicio + timedelta(days=dias - 1))

    @api.model
    def dados_ferias(self, slip):
        """Período, abono, composição da remuneração e prazo de pagamento."""
        slip.ensure_one()
        contrato = slip.contract_id
        alocacao = slip.l10n_br_ferias_allocation_id
        inicio, fim = self.periodo_gozo(slip)
        dias_gozados = slip.l10n_br_dias_ferias_gozadas
        dias_abono = slip.l10n_br_dias_ferias_vendidas
        linhas = {ln.code: ln.total for ln in slip.line_ids}
        media = slip._l10n_br_media_habitual(slip._l10n_br_codes_media_habitual())
        adicionais = slip._l10n_br_adicionais_fixos(contrato)
        remuneracao = contrato.wage + media + adicionais
        fracoes = self._fracoes(slip)
        return {
            "aquisitivo_inicio": alocacao.date_from if alocacao else False,
            "aquisitivo_fim": alocacao.date_to if alocacao else False,
            "dias_direito": alocacao.number_of_days if alocacao else 0,
            "gozo_inicio": inicio,
            "gozo_fim": fim,
            "retorno": fim + timedelta(days=1),
            "dias_gozados": dias_gozados,
            "dias_abono": dias_abono,
            "valor_abono": linhas.get("ABONO_PECUNIARIO", 0.0),
            "terco_abono": linhas.get("ADICIONAL_ABONO", 0.0),
            "valor_ferias": linhas.get("FERIAS", 0.0),
            "terco_ferias": linhas.get("ADICIONAL_FERIAS", 0.0),
            "salario": contrato.wage,
            "media": media,
            "adicionais": adicionais,
            "remuneracao": remuneracao,
            "valor_dia": round(remuneracao / 30, 2),
            "fracao": fracoes.ids.index(slip.id) + 1 if slip in fracoes else 1,
            "fracoes": max(len(fracoes), 1),
            "pagar_ate": inicio - timedelta(days=DIAS_ANTECEDENCIA_PAGAMENTO),
        }

    @api.model
    def _fracoes(self, slip):
        """Recibos (não cancelados) da mesma alocação, na ordem do gozo."""
        if not slip.l10n_br_ferias_allocation_id:
            return slip
        return (
            self.env["hr.payslip"]
            .search(
                [
                    (
                        "l10n_br_ferias_allocation_id",
                        "=",
                        slip.l10n_br_ferias_allocation_id.id,
                    ),
                    ("state", "!=", "cancel"),
                    ("l10n_br_fora_de_vigor", "=", False),
                    ("l10n_br_dias_periodo_gozado", ">", 0),
                ]
            )
            .sorted(lambda p: (p.date_from, p.id))
        )


class ReportAvisoFerias(models.AbstractModel):
    _name = "report.l10n_br_hr_payroll_report.report_aviso_ferias"
    _description = "Dados do aviso de férias"

    @api.model
    def _get_report_values(self, docids, data=None):
        docs = self.env["hr.payslip"].browse(docids)
        return {
            "doc_ids": docids,
            "doc_model": "hr.payslip",
            "docs": docs,
            "aviso": {slip.id: self.dados_aviso(slip) for slip in docs},
        }

    @api.model
    def dados_aviso(self, slip, data_emissao=None):
        """Período de gozo, data mínima de comunicação e situação do prazo.

        Emitir com menos de 30 dias de antecedência não é bloqueado: o aviso
        sai marcado como fora do prazo, para o RH decidir (art. 135 da CLT).
        """
        slip.ensure_one()
        recibo = self.env["report.l10n_br_hr_payroll_report.report_recibo_ferias"]
        ferias = recibo.dados_ferias(slip)
        emissao = data_emissao or fields.Date.context_today(slip)
        inicio = ferias["gozo_inicio"]
        minima = inicio - timedelta(days=DIAS_ANTECEDENCIA_AVISO)
        antecedencia = (inicio - emissao).days
        return {
            "ferias": ferias,
            "emissao": emissao,
            "data_minima": minima,
            "antecedencia": antecedencia,
            "fora_do_prazo": antecedencia < DIAS_ANTECEDENCIA_AVISO,
            "dias_antecedencia_minima": DIAS_ANTECEDENCIA_AVISO,
        }
