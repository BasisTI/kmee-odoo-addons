# Copyright 2024 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import api, fields, models


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
            or "contribuicao_sindical" in (r.condition_python or "")
            or "contribuicao_sindical" in (r.amount_python_compute or "")
            for r in self._get_salary_rules()
        )

    def _l10n_br_contribuicao_snapshot(self):
        """O que 617 e 602 dão a cada holerite: só a diferença tem efeito."""
        return {
            s.id: tuple(
                s.contract_id._l10n_br_contribuicao_resolver(s._get_competencia(), t)
                for t in ("assistencial", "sindical")
            )
            for s in self
        }

    @api.model
    def _l10n_br_contribuicao_guardar(self, holerites, operacao):
        """Executa ``operacao()``; só os holerites cuja 617/602 mudou são aplicados.

        Mudança sem efeito (valor individual de vigência que não cobre a
        competência, fim de experiência anterior a ela) não recalcula nem recusa.
        """
        holerites = holerites.sudo().filtered(
            lambda s: s.date_to and s.contract_id and s._l10n_br_le_cct()
        )
        antes = holerites._l10n_br_contribuicao_snapshot()
        res = operacao()
        holerites = holerites.exists()
        depois = holerites._l10n_br_contribuicao_snapshot()
        mudaram = holerites.filtered(lambda s: antes[s.id] != depois[s.id])
        self.env["l10n.br.hr.collective.convention"]._cct_aplicar_aos_holerites(mudaram)
        return res

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

        ``tools.br.contribuicao_sindical(contract, tipo)``: valor devido pelo
        contrato da contribuição do tipo (``assistencial`` = 617, ``sindical`` =
        602, ``confederativa``) cadastrada para o sindicato da CCT no mês do
        holerite, com a oposição e a marca de sindicalista do funcionário, as
        isenções da CCT e o valor individual do 602; 0.0 em branco.
        ``tools.br.contribuicao_sindical_detalhe(contract, tipo)`` devolve
        ``(valor, motivo)``: ``valor`` ``None`` é célula em branco (sem CCT, sem
        cadastro e sem valor individual), distinta do 0.0 de isenção; a condição
        da regra usa ``valor is not None``.
        """
        tools = super()._get_tools_dict()
        competencia = self._get_competencia()

        def cct(contrato):
            return contrato._l10n_br_cct_vigente(competencia)

        def contribuicao_sindical_detalhe(contrato, tipo):
            return contrato._l10n_br_contribuicao_resolver(competencia, tipo)

        def contribuicao_sindical(contrato, tipo):
            return contribuicao_sindical_detalhe(contrato, tipo)[0] or 0.0

        tools["br"].cct = cct
        tools["br"].contribuicao_sindical = contribuicao_sindical
        tools["br"].contribuicao_sindical_detalhe = contribuicao_sindical_detalhe
        return tools
