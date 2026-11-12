# Copyright 2024 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import _, fields, models
from odoo.exceptions import UserError


class HrPayslip(models.Model):
    _inherit = "hr.payslip"

    l10n_br_esocial_s1200_id = fields.Many2one(
        "l10n_br.esocial.s1200",
        string="S-1200 eSocial",
        readonly=True,
    )
    l10n_br_esocial_s1210_id = fields.Many2one(
        "l10n_br.esocial.s1210",
        string="S-1210 eSocial",
        readonly=True,
    )
    l10n_br_esocial_data_pagamento = fields.Date(
        string="Data de Pagamento",
        tracking=True,
        help="Data em que o líquido foi efetivamente pago. É o regime de caixa "
        "do S-1210: a competência do evento de pagamento vem desta data, não "
        "da competência da folha.",
    )

    def _esocial_exigir_rubrica_maternidade(self):
        """Recusa o holerite com dias de licença-maternidade sem a rubrica própria.

        Vale só para a estrutura que tem a rubrica (mensal CLT/Estatutário).

        Holerite calculado antes da TG-87 paga o salário da licença como salário
        comum (natureza 1000, incidência 11) e não tem ``SALARIO_MATERNIDADE``.
        Declará-lo assim faria a DCTFWeb perder, em silêncio, a dedução do
        salário-maternidade pago pelo empregador. A divisão por dias no S-1200
        foi removida (um mecanismo só), então o holerite precisa ser recalculado.
        """
        self.ensure_one()
        if not self.contract_id or not self.date_from or not self.date_to:
            return
        # Só a estrutura que paga o salário na rubrica própria (a mensal CLT e a
        # Estatutário) exige a linha. 13º, rescisão, férias e estruturas sem a
        # rubrica não a têm por desenho e o recálculo não a criaria.
        if not any(r.code == "SALARIO_MATERNIDADE" for r in self.struct_id.rule_ids):
            return
        if not self._l10n_br_dias_maternidade(self.contract_id):
            return
        if any(ln.code == "SALARIO_MATERNIDADE" and ln.total for ln in self.line_ids):
            return
        raise UserError(
            _(
                "O holerite %(holerite)s tem dias de licença-maternidade no "
                "período, mas não tem a rubrica SALARIO_MATERNIDADE: o salário "
                "desses dias iria ao S-1200 como salário comum e a dedução do "
                "salário-maternidade se perderia na DCTFWeb. Volte o holerite "
                "para rascunho, recalcule (a estrutura precisa ter a rubrica "
                "Salário-Maternidade) e confirme de novo.",
                holerite=self.number or self.name,
            )
        )

    def action_esocial_gerar_s1200(self):
        """Generate S-1200 event for selected confirmed payslips."""
        payslips = self.filtered(lambda p: p.state == "done")
        if not payslips:
            raise UserError(
                _("Selecione apenas holerites confirmados (estado 'Feito').")
            )

        # Group by employee + period
        groups = {}
        for slip in payslips:
            key = (slip.employee_id.id, slip.date_from.strftime("%Y-%m"))
            groups.setdefault(key, self.env["hr.payslip"])
            groups[key] |= slip

        created_events = self.env["l10n_br.esocial.evento"]
        for (emp_id, per_apur), slips in groups.items():
            s1200 = self.env["l10n_br.esocial.s1200"].create(
                {
                    "employee_id": emp_id,
                    "payslip_ids": [(6, 0, slips.ids)],
                    "per_apur": per_apur,
                    "ind_apuracao": "1",
                    "company_id": slips[0].company_id.id,
                }
            )
            evento = s1200.action_gerar_evento()
            created_events |= evento
            slips.write({"l10n_br_esocial_s1200_id": s1200.id})

        return self._action_esocial_eventos(created_events)

    def _action_esocial_eventos(self, eventos):
        """Abre o(s) evento(s) gerado(s)."""
        if len(eventos) == 1:
            return {
                "type": "ir.actions.act_window",
                "res_model": "l10n_br.esocial.evento",
                "res_id": eventos.id,
                "view_mode": "form",
            }
        return {
            "type": "ir.actions.act_window",
            "res_model": "l10n_br.esocial.evento",
            "view_mode": "list,form",
            "domain": [("id", "in", eventos.ids)],
        }

    # ── S-1210 — pagamentos (regime de caixa) ──────────────────────────────

    def _esocial_valor_liquido(self):
        """Líquido pago do holerite (rubrica NET)."""
        self.ensure_one()
        linhas = self.line_ids.filtered(lambda linha: linha.code == "NET")
        if not linhas:
            raise UserError(
                _(
                    "Holerite %(nome)s não possui a rubrica de líquido (NET). "
                    "Sem o líquido pago não é possível montar o S-1210."
                )
                % {"nome": self.number or self.display_name}
            )
        return sum(linhas.mapped("total"))

    def _esocial_s1200_para_pagamento(self):
        """S-1200 aceito que este pagamento liquida."""
        self.ensure_one()
        s1200 = self.l10n_br_esocial_s1200_id
        if not s1200:
            raise UserError(
                _(
                    "Holerite %(nome)s não possui S-1200 gerado. O S-1210 "
                    "aponta para o demonstrativo do S-1200 da competência, "
                    "então a apuração precisa vir primeiro."
                )
                % {"nome": self.number or self.display_name}
            )
        if s1200.evento_id.state != "success":
            raise UserError(
                _(
                    "O S-1200 do holerite %(nome)s ainda não foi aceito pelo "
                    "eSocial (situação atual: %(estado)s). O governo rejeita o "
                    "S-1210 cujo demonstrativo não existe na base dele."
                )
                % {
                    "nome": self.number or self.display_name,
                    "estado": s1200.evento_id.state or _("sem evento"),
                }
            )
        return s1200

    def _esocial_dados_pagamento(self):
        """Valores do infoPgto correspondente a este holerite."""
        self.ensure_one()
        s1200 = self._esocial_s1200_para_pagamento()
        return {
            "dt_pgto": self.l10n_br_esocial_data_pagamento,
            "tp_pgto": "1",
            "per_ref": s1200.per_apur,
            "ide_dm_dev": s1200.get_ide_dm_dev(),
            "vr_liq": self._esocial_valor_liquido(),
            "payslip_id": self.id,
            "s1200_id": s1200.id,
        }

    def action_esocial_gerar_s1210(self):
        """Gera os eventos S-1210 dos holerites pagos selecionados.

        O agrupamento é por beneficiário e competência de PAGAMENTO (regime de
        caixa), e não por competência da folha: dois holerites de meses
        diferentes pagos no mesmo mês vão no mesmo S-1210, cada um no seu
        demonstrativo.
        """
        payslips = self.filtered(lambda slip: slip.state == "done")
        if not payslips:
            raise UserError(
                _("Selecione apenas holerites confirmados (estado 'Feito').")
            )
        sem_data = payslips.filtered(
            lambda slip: not slip.l10n_br_esocial_data_pagamento
        )
        if sem_data:
            raise UserError(
                _(
                    "Informe a Data de Pagamento nos holerites abaixo antes de "
                    "gerar o S-1210 (o evento é por regime de caixa):\n%(lista)s"
                )
                % {
                    "lista": "\n".join(
                        "- %s" % (slip.number or slip.display_name) for slip in sem_data
                    )
                }
            )

        grupos = {}
        for slip in payslips:
            chave = (
                slip.employee_id.id,
                slip.l10n_br_esocial_data_pagamento.strftime("%Y-%m"),
                slip.company_id.id,
            )
            grupos.setdefault(chave, self.env["hr.payslip"])
            grupos[chave] |= slip

        eventos = self.env["l10n_br.esocial.evento"]
        for (employee_id, per_apur, company_id), slips in grupos.items():
            s1210 = self.env["l10n_br.esocial.s1210"].create(
                {
                    "employee_id": employee_id,
                    "per_apur": per_apur,
                    "company_id": company_id,
                    "pagamento_ids": [
                        (0, 0, slip._esocial_dados_pagamento()) for slip in slips
                    ],
                }
            )
            eventos |= s1210.action_gerar_evento()
            slips.write({"l10n_br_esocial_s1210_id": s1210.id})

        return self._action_esocial_eventos(eventos)
