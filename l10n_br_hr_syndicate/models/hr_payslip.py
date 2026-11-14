# Copyright 2024 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import models


class HrPayslip(models.Model):
    _inherit = "hr.payslip"

    def _get_tools_dict(self):
        """Entrega às regras salariais a CCT vigente na competência.

        ``tools.br.cct(contract)``: a CCT do contrato vigente na competência do
        holerite, ou um registro vazio sem CCT (``if cct:`` decide se a regra usa
        a CCT ou o que usava antes). Os valores saem dos campos da CCT
        (``cct.assistencial_amount``, ``cct.monthly_fee_amount``,
        ``cct.vt_employee_pct``, ``cct.dsr_days_per_week``,
        ``cct.vavr_rate(salario)``, ``cct.wage_floor_for(cargo)``...).

        ``tools.br.contribuicao_sindical(contract, tipo)``: valor da contribuição
        do tipo (``assistencial``, ``confederativa`` ou ``sindical``) cadastrada
        para o sindicato da CCT no mês do holerite; 0.0 sem CCT ou sem cadastro.
        """
        tools = super()._get_tools_dict()
        competencia = self._get_competencia()

        def cct(contrato):
            return contrato._l10n_br_cct_vigente(competencia)

        def contribuicao_sindical(contrato, tipo):
            convencao = cct(contrato)
            if not convencao or not competencia:
                return 0.0
            contribuicoes = self.env["l10n.br.hr.syndicate.contribution"].search(
                [
                    ("partner_union_id", "=", convencao.partner_union_id.id),
                    ("year", "=", competencia.year),
                    ("month", "=", str(competencia.month)),
                    ("contribution_type", "=", tipo),
                ]
            )
            return sum(c.amount_for(contrato.wage) for c in contribuicoes)

        tools["br"].cct = cct
        tools["br"].contribuicao_sindical = contribuicao_sindical
        return tools
