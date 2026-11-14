# Copyright 2024 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import fields, models


class HrPayslip(models.Model):
    _inherit = "hr.payslip"

    l10n_br_cct_aviso = fields.Char(
        string="Aviso da CCT",
        readonly=True,
        copy=False,
        help="Preenchido quando nenhuma CCT cobre a competência e o holerite usou "
        "a última CCT vencida do sindicato (padrão até a decisão do DP): traz o "
        "nome e o fim da vigência da CCT usada.",
    )

    def _l10n_br_le_cct(self):
        """A estrutura do holerite tem regra que lê a CCT (ou a contribuição)."""
        self.ensure_one()
        return any(
            "br.cct(" in (r.condition_python or "")
            or "br.cct(" in (r.amount_python_compute or "")
            or "contribuicao_sindical(" in (r.condition_python or "")
            or "contribuicao_sindical(" in (r.amount_python_compute or "")
            for r in self._get_salary_rules()
        )

    def _l10n_br_cct_aviso_texto(self, cct, motivo):
        dados = {
            "cct": cct.name,
            "ini": fields.Date.to_string(cct.date_start),
            "fim": fields.Date.to_string(cct.date_end),
        }
        if motivo == "vencida":
            return self.env._(
                "Nenhuma CCT cobre a competência: usada a última vencida, "
                "%(cct)s (vigência até %(fim)s).",
                **dados,
            )
        if motivo == "futura":
            return self.env._(
                "Nenhuma CCT cobre a competência (anterior à primeira): usada a "
                "primeira, %(cct)s (vigência de %(ini)s).",
                **dados,
            )
        return self.env._(
            "O sindicato não tem CCT ativa: usada a CCT arquivada %(cct)s "
            "(vigência de %(ini)s a %(fim)s).",
            **dados,
        )

    def compute_sheet(self):
        res = super().compute_sheet()
        for slip in self:
            aviso = False
            if slip.contract_id and slip._l10n_br_le_cct():
                cct, motivo = slip.contract_id._l10n_br_cct_resolver(
                    slip._get_competencia()
                )
                if motivo:
                    aviso = self._l10n_br_cct_aviso_texto(cct, motivo)
            if slip.l10n_br_cct_aviso != aviso:
                slip.l10n_br_cct_aviso = aviso
        return res

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
