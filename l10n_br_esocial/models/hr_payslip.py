# Copyright 2024 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import _, api, fields, models
from odoo.exceptions import UserError

# Estados do evento que ainda declaram valores ao eSocial (não retificado, não
# excluído, não recusado).
EVENTO_VIGENTE = ("draft", "validated", "pending", "sent", "success")


class HrPayslip(models.Model):
    _inherit = "hr.payslip"

    l10n_br_esocial_s1200_id = fields.Many2one(
        "l10n_br.esocial.s1200",
        string="S-1200 eSocial",
        readonly=True,
        copy=False,
    )
    l10n_br_esocial_s1210_id = fields.Many2one(
        "l10n_br.esocial.s1210",
        string="S-1210 eSocial",
        readonly=True,
        copy=False,
    )
    l10n_br_esocial_s2299_ids = fields.One2many(
        "l10n_br.esocial.s2299",
        "payslip_id",
        string="S-2299 eSocial",
        readonly=True,
    )
    l10n_br_esocial_data_pagamento = fields.Date(
        string="Data de Pagamento",
        tracking=True,
        help="Data em que o líquido foi efetivamente pago. É o regime de caixa "
        "do S-1210: a competência do evento de pagamento vem desta data, não "
        "da competência da folha.",
    )

    l10n_br_esocial_a_retificar = fields.Boolean(
        string="eSocial a retificar",
        compute="_compute_l10n_br_esocial_a_retificar",
        store=True,
        help="Holerite fora de vigor (estornado) que ainda tem S-1200, S-1210 ou "
        "S-2299 gerado e não retificado nem excluído: o evento declara valores "
        "que a folha desfez. Gere o S-1200 do holerite que o substitui "
        "(retificação, com o recibo do evento aceito) ou exclua o evento por "
        "S-3000.",
    )

    @api.depends(
        "l10n_br_fora_de_vigor",
        "l10n_br_esocial_s1200_id.evento_id.state",
        "l10n_br_esocial_s1210_id.evento_id.state",
        "l10n_br_esocial_s2299_ids.evento_id.state",
    )
    def _compute_l10n_br_esocial_a_retificar(self):
        for slip in self:
            eventos = (
                slip.l10n_br_esocial_s1200_id.evento_id
                | slip.l10n_br_esocial_s1210_id.evento_id
                | slip.l10n_br_esocial_s2299_ids.evento_id
            )
            slip.l10n_br_esocial_a_retificar = bool(
                slip.l10n_br_fora_de_vigor
                and not slip.l10n_br_estorno
                and eventos.filtered(lambda e: e.state in EVENTO_VIGENTE)
            )

    def refund_sheet(self):
        """O estorno invalida os eventos ainda não transmitidos do estornado."""
        res = super().refund_sheet()
        self._esocial_invalidar_eventos_nao_transmitidos()
        return res

    def _esocial_invalidar_eventos_nao_transmitidos(self):
        """Tira do lote o evento validado do holerite estornado e avisa.

        Evento em rascunho ou validado ainda não foi ao governo, mas declara o
        que a folha desfez. Volta a rascunho (e sai do lote); a validação passa a
        recusá-lo enquanto o holerite estiver fora de vigor.
        """
        for slip in self.filtered("l10n_br_fora_de_vigor"):
            eventos = (
                slip.l10n_br_esocial_s1200_id.evento_id
                | slip.l10n_br_esocial_s1210_id.evento_id
                | slip.l10n_br_esocial_s2299_ids.evento_id
            ).filtered(lambda e: e.state in ("draft", "validated"))
            for evento in eventos:
                evento.write({"state": "draft", "lote_id": False})
                evento.message_post(
                    body=_(
                        "O holerite %(slip)s foi estornado antes da transmissão: "
                        "este evento declara o que a folha desfez e não pode ser "
                        "validado. Descarte-o e gere o do holerite que o substitui."
                    )
                    % {"slip": slip.number or slip.name}
                )

    def _esocial_competencia_fechada(self, company, per_apur):
        """Competência com S-1299 aceito e sem S-1298 aceito depois dele."""
        eventos = self.env["l10n_br.esocial.evento"]
        base = [
            ("company_id", "=", company.id),
            ("per_apur", "=", per_apur),
            ("state", "=", "success"),
        ]
        fechamento = eventos.search(
            base + [("tipo", "=", "S-1299")], order="id desc", limit=1
        )
        if not fechamento:
            return False
        reabertura = eventos.search(
            base + [("tipo", "=", "S-1298"), ("id", ">", fechamento.id)], limit=1
        )
        return not reabertura

    def _esocial_exigir_competencia_aberta(self, company, per_apur):
        """MOS S-1.3, S-1200 item 31.3: evento de movimento encerrado só após S-1298."""
        if self._esocial_competencia_fechada(company, per_apur):
            raise UserError(
                _(
                    "A competência %(per)s está fechada (S-1299 aceito, sem "
                    "S-1298 depois). O eSocial só aceita evento periódico dela "
                    "depois da reabertura (S-1298): reabra a competência antes de "
                    "gerar o evento."
                )
                % {"per": per_apur}
            )

    def _esocial_exigir_sem_s1210_vigente(self, anterior):
        """O S-1210 que referencia o demonstrativo a retificar sai antes (S-3000).

        MOS S-1.3, cap. I item 15.2 (p. 44) e S-1200 item 31.1 (p. 158): a
        retificação do S-1200 exige a prévia exclusão do S-1210 que o referencia,
        salvo só inclusão de novo demonstrativo ou demonstrativo sem S-1210. Aqui
        o demonstrativo do estornado é substituído, então o S-1210 sai antes e é
        reenviado depois.
        """
        pagamentos = self.env["l10n_br.esocial.s1210.pagamento"].search(
            [("s1200_id", "=", anterior.id)]
        )
        s1210s = pagamentos.s1210_id.filtered(
            lambda s: s.evento_id.state in ("pending", "sent", "success")
        )
        if s1210s:
            raise UserError(
                _(
                    "O S-1200 %(s1200)s a retificar tem S-1210 transmitido que "
                    "referencia o demonstrativo dele (%(s1210)s). O eSocial só "
                    "aceita o retificador depois da exclusão desse S-1210: gere o "
                    "S-3000 dele, espere o aceite, gere o S-1200 retificador e "
                    "reenvie o S-1210 (MOS S-1.3, item 15.2 do cap. I)."
                )
                % {
                    "s1200": anterior.evento_id.name,
                    "s1210": ", ".join(s1210s.mapped("evento_id.name")),
                }
            )

    def _esocial_em_vigor(self):
        """Holerites confirmados e em vigor (o par estornado não vai ao eSocial).

        O estorno e o holerite que ele desfez se anulam: declarar os dois, ou só
        o original, somaria no eSocial o que a folha já desfez.
        """
        confirmados = self.filtered(lambda slip: slip.state == "done")
        if not confirmados:
            raise UserError(
                _("Selecione apenas holerites confirmados (estado 'Feito').")
            )
        vigentes = confirmados.filtered(lambda slip: not slip.l10n_br_fora_de_vigor)
        if not vigentes:
            raise UserError(
                _(
                    "Os holerites selecionados estão fora de vigor (estorno ou "
                    "holerite estornado) e não vão ao eSocial. Gere o evento do "
                    "holerite que substitui o estornado; o evento já gerado do "
                    "estornado se retifica por ele ou se exclui por S-3000."
                )
            )
        return vigentes

    def _esocial_evento_anterior(self, modelo, dominio_extra):
        """Evento aceito do estornado que o novo evento deve retificar.

        Só vale quando o evento aceito tem recibo e declara algum holerite fora
        de vigor; se o retorno do anterior ainda não chegou, não há recibo a
        retificar e a geração espera.
        """
        anteriores = self.env[modelo].search(
            [("evento_id", "!=", False)] + dominio_extra, order="id desc"
        )
        anteriores = anteriores.filtered(
            lambda ev: ev.evento_id.state in ("pending", "sent", "success")
            and ev._esocial_slips().filtered("l10n_br_fora_de_vigor")
        )
        if not anteriores:
            return anteriores
        mais_recente = anteriores[0]
        evento = mais_recente.evento_id
        if evento.state != "success" or not evento.nr_recibo:
            raise UserError(
                _(
                    "O %(tipo)s %(nome)s do holerite estornado ainda não foi "
                    "aceito pelo eSocial (situação: %(estado)s). Sem o recibo "
                    "dele não há o que retificar: espere o retorno do lote."
                )
                % {
                    "tipo": evento.tipo,
                    "nome": evento.name,
                    "estado": evento.state,
                }
            )
        return mais_recente

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
        payslips = self._esocial_em_vigor()
        # Segunda chamada não duplica o retificador: o holerite que já tem um
        # retificador vigente fica como está.
        pendentes = payslips.filtered(
            lambda slip: slip.l10n_br_esocial_s1200_id.ind_retif == "2"
            and slip.l10n_br_esocial_s1200_id.evento_id.state
            in ("draft", "validated", "pending", "sent")
        )
        if pendentes == payslips:
            raise UserError(
                _(
                    "O holerite já tem S-1200 retificador gerado (%(evento)s). "
                    "Use o evento existente em vez de gerar outro."
                )
                % {"evento": pendentes[0].l10n_br_esocial_s1200_id.evento_id.name}
            )
        payslips -= pendentes

        # Group by employee + period
        groups = {}
        for slip in payslips:
            key = (slip.employee_id.id, slip.date_from.strftime("%Y-%m"))
            groups.setdefault(key, self.env["hr.payslip"])
            groups[key] |= slip

        created_events = self.env["l10n_br.esocial.evento"]
        for (emp_id, per_apur), slips in groups.items():
            company = slips[0].company_id
            self._esocial_exigir_competencia_aberta(company, per_apur)
            anterior = self._esocial_evento_anterior(
                "l10n_br.esocial.s1200",
                [
                    ("employee_id", "=", emp_id),
                    ("per_apur", "=", per_apur),
                    ("ind_apuracao", "=", "1"),
                    ("company_id", "=", company.id),
                ],
            )
            vals = {
                "employee_id": emp_id,
                "per_apur": per_apur,
                "ind_apuracao": "1",
                "company_id": company.id,
            }
            if anterior:
                self._esocial_exigir_sem_s1210_vigente(anterior)
                # O retificador substitui o evento inteiro da competência: leva
                # também os holerites que continuam em vigor no evento anterior.
                slips |= anterior.payslip_ids.filtered(
                    lambda slip: slip.state == "done" and not slip.l10n_br_fora_de_vigor
                )
                vals.update(
                    ind_retif="2",
                    nr_recibo=anterior.evento_id.nr_recibo,
                    evento_retificado_id=anterior.evento_id.id,
                )
            vals["payslip_ids"] = [(6, 0, slips.ids)]
            s1200 = self.env["l10n_br.esocial.s1200"].create(vals)
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

    def _esocial_tp_rend(self, linha=None):
        """Tipo de rendimento (TS_tpRendDep) do holerite ou de uma linha dele.

        11 = remuneração mensal, 12 = 13º salário, 13 = férias. Vem da estrutura
        do holerite (``13_*`` e ``FERIAS``); na rescisão, que traz o 13º
        proporcional junto, a linha de código ``*_13`` é do 13º.
        """
        self.ensure_one()
        estrutura = self.struct_id.code or ""
        if estrutura.startswith("13_"):
            return "12"
        if estrutura == "FERIAS":
            return "13"
        if linha is not None and (linha.code or "").endswith("_13"):
            return "12"
        return "11"

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
        payslips = self._esocial_em_vigor()
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
            self._esocial_exigir_competencia_aberta(
                self.env["res.company"].browse(company_id), per_apur
            )
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

    # ── S-2299 — desligamento a partir da rescisão ─────────────────────────

    def action_esocial_gerar_s2299(self):
        """Gera o S-2299 dos holerites de rescisão, ligado a cada holerite.

        A ligação (``payslip_id``) é o que faz o ``indPagtoAPI`` e a data
        projetada do aviso seguirem a folha. Data do desligamento = fim do
        período da rescisão; o motivo vem do contrato.
        """
        rescisoes = self.filtered(
            lambda slip: slip.state == "done" and slip.struct_id.code == "RESCISAO"
        )
        payslips = rescisoes.filtered(lambda slip: not slip.l10n_br_fora_de_vigor)
        if rescisoes and not payslips:
            raise UserError(
                _(
                    "A rescisão selecionada está fora de vigor (estorno ou "
                    "estornada) e não vai ao eSocial. O S-2299 já gerado do "
                    "holerite estornado fica marcado como a retificar: exclua-o "
                    "por S-3000 e gere o S-2299 da rescisão que o substitui."
                )
            )
        if not payslips:
            raise UserError(
                _("Selecione holerites de rescisão confirmados (estado 'Feito').")
            )
        eventos = self.env["l10n_br.esocial.evento"]
        for slip in payslips:
            motivo = slip.contract_id.l10n_br_esocial_motivo_deslig_id
            if not motivo:
                raise UserError(
                    _(
                        "Informe o Motivo Desligamento eSocial no contrato de "
                        "'%(name)s' antes de gerar o S-2299."
                    )
                    % {"name": slip.employee_id.name}
                )
            s2299 = self.env["l10n_br.esocial.s2299"].create(
                {
                    "employee_id": slip.employee_id.id,
                    "contract_id": slip.contract_id.id,
                    "dt_deslig": slip.date_to,
                    "motivo_desligamento_id": motivo.id,
                    "payslip_id": slip.id,
                    "company_id": slip.company_id.id,
                }
            )
            eventos |= s2299.action_gerar_evento()
        return self._action_esocial_eventos(eventos)
