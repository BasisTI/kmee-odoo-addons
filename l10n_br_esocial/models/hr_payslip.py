# Copyright 2024 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError

# Estados do evento que ainda declaram valores ao eSocial (não retificado, não
# excluído, não recusado).
# Regras do abono pecuniário e do terço dele: a parte futura vai no par próprio
# de adiantamento/desconto (TG-152#P2).
CODIGOS_ABONO = ("ABONO_PECUNIARIO", "ADICIONAL_ABONO")
EVENTO_VIGENTE = ("draft", "validated", "pending", "sent", "success")


class HrPayslip(models.Model):
    _inherit = "hr.payslip"

    l10n_br_esocial_s1200_id = fields.Many2one(
        "l10n_br.esocial.s1200",
        string="S-1200 eSocial",
        readonly=True,
        copy=False,
    )
    l10n_br_esocial_s1200_ids = fields.Many2many(
        "l10n_br.esocial.s1200",
        "hr_payslip_l10n_br_esocial_s1200_rel",
        "hr_payslip_id",
        "l10n_br_esocial_s1200_id",
        string="S-1200 eSocial (todas as competências)",
        readonly=True,
        copy=False,
        help="Todos os S-1200 que declaram este holerite. O recibo de férias que "
        "atravessa o mês (e o adiantamento pago em mês anterior) tem um S-1200 por "
        "competência (MOS S-1.3, S-1010, item 23, pp. 112-114); o campo "
        "'S-1200 eSocial' é o da primeira.",
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
        "(retificação, com o recibo do evento aceito). Evento aceito se exclui "
        "por S-3000; evento ainda não transmitido (rascunho ou validado) se "
        "apaga, o que só o gestor de folha pode fazer.",
    )

    @api.depends(
        "l10n_br_fora_de_vigor",
        "l10n_br_esocial_s1200_id.evento_id.state",
        "l10n_br_esocial_s1200_ids.evento_id.state",
        "l10n_br_esocial_s1210_id.evento_id.state",
        "l10n_br_esocial_s2299_ids.evento_id.state",
    )
    def _compute_l10n_br_esocial_a_retificar(self):
        for slip in self:
            eventos = (
                slip.l10n_br_esocial_s1200_id.evento_id
                | slip.l10n_br_esocial_s1200_ids.evento_id
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
                | slip.l10n_br_esocial_s1200_ids.evento_id
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

    def _esocial_exigir_mesmo_mes_do_s2299(self, anterior, vals):
        """Retificador do S-2299 mantém o mês do desligamento.

        MOS S-1.3, cap. I item 15.2 (p. 43): ``dtDeslig`` que implica mudança de
        mês não se retifica; o evento é excluído e um novo é enviado (o retificador
        tem o mesmo período de apuração do retificado).
        """
        antigo = anterior.dt_deslig
        novo = fields.Date.to_date(vals["dt_deslig"])
        if (antigo.year, antigo.month) != (novo.year, novo.month):
            raise UserError(
                _(
                    "O S-2299 %(s2299)s aceito tem desligamento em %(antigo)s e a "
                    "rescisão que o substitui, em %(novo)s: o eSocial não aceita "
                    "retificar o S-2299 com mudança de mês (MOS S-1.3, cap. I "
                    "item 15.2). Gere o S-3000 do S-2299 aceito (antes, o S-3000 "
                    "dos S-1210 de tpPgto 2 que apontam para ele), espere o aceite "
                    "e gere o S-2299 novo."
                )
                % {
                    "s2299": anterior.evento_id.name,
                    "antigo": antigo.strftime("%m/%Y"),
                    "novo": novo.strftime("%m/%Y"),
                }
            )

    def _esocial_exigir_sem_s1210_vigente_s2299(self, anterior, vals):
        """O S-1210 ``tpPgto`` 2 de demonstrativo que muda ou some sai antes.

        O retificador troca os demonstrativos do S-2299 (um ``ideDmDev`` por
        holerite). O S-1210 transmitido que aponta para um demonstrativo que o
        retificador não repete ficaria sem apuração: sai antes (S-3000) e é
        reenviado depois do aceite do retificador. O que aponta para
        demonstrativo que segue igual não precisa sair (MOS S-1.3, cap. I item
        15.2, p. 44, perApur desde 09/2025).
        """
        novo = self.env["l10n_br.esocial.s2299"].new(dict(vals, ind_retif="2"))
        mantidos = {novo.get_ide_dm_dev(slip) for slip in novo._slips_verbas()}
        eventos = anterior.evento_id._s1210_dependentes(
            estados=("pending", "sent", "success"), manter_ides=mantidos
        )
        if eventos:
            raise UserError(
                _(
                    "O S-2299 %(s2299)s a retificar tem S-1210 transmitido que "
                    "aponta para demonstrativo que o retificador não repete "
                    "(%(s1210)s). O eSocial só aceita o retificador depois da "
                    "exclusão desse S-1210: gere o S-3000 dele, espere o aceite, "
                    "gere o S-2299 retificador e reenvie o S-1210."
                )
                % {
                    "s2299": anterior.evento_id.name,
                    "s1210": ", ".join(eventos.mapped("name")),
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
                    "estornado, se aceito, se retifica por ele ou se exclui por "
                    "S-3000; se ainda não foi transmitido (rascunho ou validado), "
                    "o gestor de folha o apaga."
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

    def _esocial_s2299_declarante(self):
        """S-2299 vigente que declara as verbas deste holerite (ou vazio).

        O S-2299 com ``verbasResc`` declara a remuneração do mês do
        desligamento; o leiaute recusa o S-1200 dessa competência e o
        pagamento vai no S-1210 de ``tpPgto`` 2. Vale o que o XML do evento
        declarou (``_slips_declarados``), não o que o holerite diria hoje: a
        rescisão pode ter mudado de estado depois da geração do S-2299.
        """
        self.ensure_one()
        inicio = self.date_from.replace(day=1)
        candidatos = self.env["l10n_br.esocial.s2299"].search(
            [
                ("employee_id", "=", self.employee_id.id),
                ("company_id", "=", self.company_id.id),
                ("dt_deslig", ">=", inicio),
                ("dt_deslig", "<", inicio + relativedelta(months=1)),
                ("evento_id.state", "in", EVENTO_VIGENTE),
            ]
        )
        return candidatos.filtered(lambda s2299: self in s2299._slips_declarados())[:1]

    def _esocial_s2299_a_retificar(self):
        """S-2299 vigente do mês que declara uma rescisão estornada (ou vazio).

        Holerite do mês do desligamento que o S-2299 não declarou, enquanto o
        S-2299 vigente do trabalhador ainda declara a rescisão estornada: é a
        rescisão que a substitui. O desligamento já existe no governo; o que muda
        vai na retificação do S-2299 (ou no S-3000 dele e num novo S-2299), nunca
        no S-1200 da competência do desligamento.
        """
        self.ensure_one()
        if (self.struct_id.code or "").startswith("13_"):
            return self.env["l10n_br.esocial.s2299"]
        inicio = self.date_from.replace(day=1)
        candidatos = self.env["l10n_br.esocial.s2299"].search(
            [
                ("employee_id", "=", self.employee_id.id),
                ("company_id", "=", self.company_id.id),
                ("dt_deslig", ">=", inicio),
                ("dt_deslig", "<", inicio + relativedelta(months=1)),
                ("evento_id.state", "in", EVENTO_VIGENTE),
                ("payslip_id.l10n_br_fora_de_vigor", "=", True),
            ]
        )
        return candidatos.filtered(lambda s2299: self not in s2299._slips_declarados())[
            :1
        ]

    def _esocial_msg_s1200_da_substituta(self, a_retificar):
        """Recusa do S-1200 da rescisão substituta, conforme o estado do S-2299."""
        self.ensure_one()
        retificador = self.env["l10n_br.esocial.s2299"].search(
            [
                ("evento_retificado_id", "=", a_retificar.evento_id.id),
                ("evento_id.state", "in", ("draft", "validated", "pending", "sent")),
            ],
            limit=1,
        )
        if retificador:
            if retificador.evento_id.state in ("pending", "sent"):
                proximo = _(
                    "o retificador %(evento)s já foi enviado: aguarde o retorno do "
                    "eSocial."
                ) % {"evento": retificador.evento_id.name}
            else:
                proximo = _(
                    "o retificador %(evento)s já existe e não foi transmitido: "
                    "transmita-o."
                ) % {"evento": retificador.evento_id.name}
        elif a_retificar.evento_id.state in ("pending", "sent"):
            proximo = _(
                "o S-2299 %(evento)s foi enviado e aguarda o retorno: aguarde o "
                "aceite para gerar o retificador."
            ) % {"evento": a_retificar.evento_id.name}
        else:
            proximo = _(
                "gere o S-2299 da rescisão que substitui a estornada (retificador "
                "do S-2299 aceito, com o recibo dele) ou, para recomeçar, exclua o "
                "S-2299 por S-3000 e gere um novo."
            )
        return _(
            "O holerite %(slip)s é do mês do desligamento de '%(name)s', e o "
            "S-2299 %(evento)s ainda declara a rescisão estornada. O leiaute "
            "recusa o S-1200 da competência do desligamento rescisório: %(proximo)s"
        ) % {
            "slip": self.number or self.name,
            "name": self.employee_id.name,
            "evento": a_retificar.evento_id.name,
            "proximo": proximo,
        }

    def _esocial_s1200_vigentes(self):
        """Eventos S-1200 vigentes que declaram este holerite (um por competência)."""
        self.ensure_one()
        return self.l10n_br_esocial_s1200_ids.evento_id.filtered(
            lambda evento: evento.state in EVENTO_VIGENTE
        )

    def _esocial_competencia_adiantamento(self):
        """Competência do pagamento adiantado do recibo de férias, ou ``False``.

        MOS S-1.3, S-1010, item 23 (pp. 112-114), exemplos (a) e (c): quando o
        recibo é pago em competência anterior à de parte do gozo, o S-1200 da
        competência do pagamento leva o adiantamento (natureza 1015) e o de cada
        competência seguinte, o desconto dele (9221). A data de pagamento vem de
        ``l10n_br_esocial_data_pagamento`` (a mesma do S-1210): sem ela, ou com o
        pagamento no mês do gozo e nada depois dele, não há adiantamento (opção 2
        do exemplo (b)).
        """
        self.ensure_one()
        if self.struct_id.code != "FERIAS" or not self.l10n_br_esocial_data_pagamento:
            return False
        pago = self.l10n_br_esocial_data_pagamento.strftime("%Y-%m")
        gozo = [per for per, _dias in self._l10n_br_competencias_ferias()]
        if not any(per > pago for per in gozo):
            return False
        return pago

    def _esocial_competencias_s1200(self):
        """Períodos de apuração (AAAA-MM) cujo S-1200 declara este holerite.

        As competências do gozo (``_l10n_br_competencias_ferias``, a mesma função
        da base da multa do FGTS) e, antes delas, a do pagamento adiantado.
        """
        self.ensure_one()
        pers = [per for per, _dias in self._l10n_br_competencias_ferias()]
        pago = self._esocial_competencia_adiantamento()
        if pago and pago not in pers:
            pers.insert(0, pago)
        return pers

    def _esocial_competencia_ir(self):
        """Competência cujo S-1200 leva a retenção e as deduções do IR do recibo.

        O IRRF é regime de caixa: o S-1210 do pagamento só referencia o
        demonstrativo do S-1200 em que o recibo foi pago, então a retenção e as
        deduções do IR ficam inteiras nele (MOS S-1.3, S-1210, item 4.1, exemplos 1
        e 2, pp. 186-188: o desconto do IR das férias vai inteiro, com
        ``codIncIRRF`` 33, no demonstrativo da antecipação, que é o pago). É a
        competência do pagamento (``l10n_br_esocial_data_pagamento``) quando o
        recibo declara essa competência; sem data de pagamento, a primeira.
        """
        self.ensure_one()
        pers = self._esocial_competencias_s1200()
        pago = False
        if self.struct_id.code == "FERIAS" and self.l10n_br_esocial_data_pagamento:
            pago = self.l10n_br_esocial_data_pagamento.strftime("%Y-%m")
        return pago if pago in pers else pers[0]

    def _esocial_linha_inss(self, line):
        """A linha é o desconto da contribuição previdenciária (``codIncCP`` 31)."""
        rule = line.salary_rule_id
        return (
            rule.l10n_br_esocial_tp_rubr == "2"
            and rule.l10n_br_esocial_cod_inc_cp == "31"
        )

    def _esocial_linha_inteira_no_pagamento(self, line):
        """Retenção do IR e deduções da base do IR (exceto o INSS) do recibo de férias.

        ``codIncIRRF`` 31 a 34 (retenção) e 4x, 5x e 6x (deduções: previdência
        complementar, pensão alimentícia, FAPI etc.). Não rateiam: vão inteiras na
        competência do pagamento (``_esocial_competencia_ir``). O INSS tem a CP por
        parte (rateado pelos dias de gozo) e a dedução dele no IR se compensa pelo
        adiantamento líquido do INSS da parte (``_esocial_liquido_da_competencia``).
        """
        if self.struct_id.code != "FERIAS" or self._esocial_linha_inss(line):
            return False
        incidencia = line.salary_rule_id.l10n_br_esocial_cod_inc_irrf or ""
        return incidencia[:1] in ("3", "4", "5", "6")

    def _esocial_valor_na_competencia(self, line, per_apur):
        """Parte da linha do recibo que cabe no S-1200 de ``per_apur`` (TG-152).

        Rateio por dias de gozo, menos a retenção e as deduções do IR, que vão
        inteiras na competência do pagamento (``_esocial_competencia_ir``).
        """
        self.ensure_one()
        if self._esocial_linha_inteira_no_pagamento(line):
            return line.total if per_apur == self._esocial_competencia_ir() else 0.0
        return self._l10n_br_ratear_valor(line.total, per_apur)

    def _esocial_liquido_da_competencia(self, per_apur, abono=False):
        """Proventos do recibo na competência, líquidos do INSS dela.

        É o valor do adiantamento (1015, soma das partes seguintes) e do desconto
        dele (9221, de cada competência seguinte). Líquido do INSS porque o INSS
        da parte é descontado na própria competência dela, com a CP 31 por parte;
        o adiantamento líquido zera o demonstrativo daquela competência e a dedução
        do INSS no IR da parte (``codIncIRRF`` 41) cancela o que o 9221 deixa de
        abater do rendimento. É o que o MOS faz no exemplo 4.1 do S-1210 (p. 186-187,
        o desconto do adiantamento é o valor líquido pago).
        """
        self.ensure_one()
        # ``abono``: só o abono pecuniário e o terço dele (par próprio de rubricas,
        # sem INSS); senão, só as demais verbas (férias e terço), líquidas do INSS.
        total = 0.0
        for line in self.line_ids:
            rule = line.salary_rule_id
            if (
                not line.total
                or not rule.l10n_br_esocial_nat_rubr_id
                or not rule.l10n_br_esocial_cod_rubr
            ):
                continue
            if rule.l10n_br_esocial_tp_rubr == "1" and line.total > 0:
                if (rule.code in CODIGOS_ABONO) == abono:
                    total += self._l10n_br_ratear_valor(line.total, per_apur)
            elif not abono and self._esocial_linha_inss(line):
                total -= abs(self._l10n_br_ratear_valor(line.total, per_apur))
        return round(total, 2)

    def _esocial_adiantamentos_ferias(self, per_apur):
        """``[(xmlid da regra, valor)]`` do 1015/9221 do recibo na competência.

        Exemplos (a) e (c) do MOS, item 23 (pp. 112-114), opção 2: na competência
        do pagamento, o adiantamento (1015) com o valor líquido das partes gozadas
        nas competências seguintes; em cada competência seguinte, o desconto dele
        (9221) da sua parte. Dois pares: o das férias e do terço (IRRF 13) e o do
        abono pecuniário e do terço dele (TG-152#P2, opção 1; sem CP nem FGTS, com a
        incidência de IRRF da rubrica do abono da empresa). Sem adiantamento, ``[]``.
        """
        self.ensure_one()
        pago = self._esocial_competencia_adiantamento()
        if not pago:
            return []
        seguintes = [
            per for per, _dias in self._l10n_br_competencias_ferias() if per > pago
        ]
        if per_apur == pago:
            pares = (
                ("hr_rule_adiantamento_ferias_esocial", False),
                ("hr_rule_adiantamento_abono_esocial", True),
            )
            pers = seguintes
        elif per_apur in seguintes:
            pares = (
                ("hr_rule_desconto_adiantamento_ferias", False),
                ("hr_rule_desconto_adiantamento_abono", True),
            )
            pers = [per_apur]
        else:
            return []
        itens = []
        for xmlid, abono in pares:
            valor = sum(self._esocial_liquido_da_competencia(p, abono) for p in pers)
            if round(valor, 2):
                itens.append(("l10n_br_esocial." + xmlid, round(valor, 2)))
        return itens

    def action_esocial_gerar_s1200(self):
        """Generate S-1200 event for selected confirmed payslips."""
        payslips = self._esocial_em_vigor()
        for slip in payslips:
            a_retificar = slip._esocial_s2299_a_retificar()
            if a_retificar:
                raise UserError(slip._esocial_msg_s1200_da_substituta(a_retificar))
        no_s2299 = payslips.filtered(lambda slip: slip._esocial_s2299_declarante())
        if no_s2299 == payslips:
            raise UserError(
                _(
                    "As verbas destes holerites estão no S-2299 do desligamento "
                    "(verbasResc): o leiaute recusa o S-1200 da competência do "
                    "desligamento rescisório. O pagamento vai no S-1210 "
                    "(tpPgto 2), apontando para o S-2299."
                )
            )
        payslips -= no_s2299
        # TG-152#P3: o recibo de férias com gozo em mais de uma competência exige a
        # data de pagamento (decide a competência do adiantamento e a da retenção
        # do IR); sem ela, o exemplo (a) do MOS ficaria sem adiantamento.
        sem_data = payslips.filtered(
            lambda slip: slip.struct_id.code == "FERIAS"
            and len(slip._l10n_br_competencias_ferias()) > 1
            and not slip.l10n_br_esocial_data_pagamento
        )
        if sem_data:
            raise UserError(
                _(
                    "O recibo de férias com gozo em mais de uma competência exige a "
                    "Data de Pagamento antes de gerar o S-1200 (ela decide o "
                    "adiantamento das férias, MOS S-1.3, S-1010, item 23, e a "
                    "competência da retenção do IR). Preencha a data em: %s."
                )
                % ", ".join(slip.number or slip.name for slip in sem_data)
            )
        # Group by employee + period. O recibo de férias que atravessa o mês entra
        # no S-1200 de cada competência em que há gozo, rateado por dias de gozo
        # (MOS S-1.3, S-1010, item 23, pp. 112-114), e no da competência do
        # pagamento adiantado; a função que decide as competências do gozo é a
        # mesma da base da multa do FGTS (``_l10n_br_competencias_ferias``). O
        # contexto ``esocial_per_apur`` limita a geração a uma competência (para
        # retificar só a segunda de um recibo que gerou dois S-1200).
        so_per_apur = self.env.context.get("esocial_per_apur")
        groups = {}
        for slip in payslips:
            for per_apur in slip._esocial_competencias_s1200():
                if so_per_apur and per_apur != so_per_apur:
                    continue
                key = (slip.employee_id.id, per_apur)
                groups.setdefault(key, self.env["hr.payslip"])
                groups[key] |= slip
        if not groups:
            raise UserError(
                _("Nenhum dos holerites selecionados tem a competência %s.")
                % so_per_apur
            )
        # Segunda chamada não duplica o retificador: a competência cujo S-1200
        # vigente já é um retificador ainda não finalizado fica como está.
        pendentes = []
        for key, slips in list(groups.items()):
            ultimo = self.env["l10n_br.esocial.s1200"].search(
                [
                    ("employee_id", "=", key[0]),
                    ("per_apur", "=", key[1]),
                    ("ind_apuracao", "=", "1"),
                    ("payslip_ids", "in", slips.ids),
                    ("evento_id", "!=", False),
                ],
                order="id desc",
                limit=1,
            )
            if ultimo.ind_retif == "2" and ultimo.evento_id.state in (
                "draft",
                "validated",
                "pending",
                "sent",
            ):
                pendentes.append(ultimo)
                del groups[key]
        if not groups:
            raise UserError(
                _(
                    "O holerite já tem S-1200 retificador gerado (%(evento)s). "
                    "Use o evento existente em vez de gerar outro."
                )
                % {"evento": pendentes[0].evento_id.name}
            )

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
            # O S-1210 aponta para o S-1200 da competência do pagamento, onde ficam
            # a retenção e as deduções do IR (``l10n_br_esocial_s1200_id``); todos
            # os S-1200 do holerite ficam em ``l10n_br_esocial_s1200_ids``.
            slips.filtered(
                lambda slip: slip._esocial_competencia_ir() == per_apur
            ).write({"l10n_br_esocial_s1200_id": s1200.id})
            if so_per_apur:
                # Retificador só desta competência (recibo novo, com a do
                # pagamento vigente e inalterada): o S-1210 do recibo novo
                # aponta para o S-1200 vigente dela.
                for slip in slips.filtered(
                    lambda slip: not slip.l10n_br_esocial_s1200_id
                    and slip._esocial_competencia_ir() != per_apur
                ):
                    slip._esocial_vincular_s1200_da_competencia_ir()

        return self._action_esocial_eventos(created_events)

    def _esocial_vincular_s1200_da_competencia_ir(self):
        """Liga o recibo ao S-1200 vigente da competência do pagamento."""
        self.ensure_one()
        vigente = self.env["l10n_br.esocial.s1200"].search(
            [
                ("employee_id", "=", self.employee_id.id),
                ("per_apur", "=", self._esocial_competencia_ir()),
                ("ind_apuracao", "=", "1"),
                ("company_id", "=", self.company_id.id),
                ("evento_id.state", "in", EVENTO_VIGENTE),
            ],
            order="id desc",
            limit=1,
        )
        if vigente:
            self.l10n_br_esocial_s1200_id = vigente.id
        return vigente

    def action_esocial_gerar_s1200_competencia(self, per_apur):
        """Gera (ou retifica) o S-1200 de uma só competência do recibo (AAAA-MM).

        Para o recibo que atravessa o mês: retifica a segunda competência sem
        mexer na primeira. Sem o contexto: ``action_esocial_gerar_s1200`` faz
        todas.
        """
        return self.with_context(esocial_per_apur=per_apur).action_esocial_gerar_s1200()

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

    def _esocial_dados_pagamento_rescisorio(self, s2299):
        """infoPgto de ``tpPgto`` 2: verbas rescisórias apuradas no S-2299."""
        self.ensure_one()
        if s2299.evento_id.state != "success":
            raise UserError(
                _(
                    "O S-2299 do holerite %(nome)s ainda não foi aceito pelo "
                    "eSocial (situação atual: %(estado)s). O governo rejeita o "
                    "S-1210 cujo demonstrativo não existe na base dele."
                )
                % {
                    "nome": self.number or self.display_name,
                    "estado": s2299.evento_id.state or _("sem evento"),
                }
            )
        return {
            "dt_pgto": self.l10n_br_esocial_data_pagamento,
            "tp_pgto": "2",
            # tpPgto 2: perRef é o mês/ano da data de desligamento.
            "per_ref": s2299.dt_deslig.strftime("%Y-%m"),
            "ide_dm_dev": s2299.get_ide_dm_dev(self),
            "vr_liq": self._esocial_valor_liquido(),
            "payslip_id": self.id,
        }

    def _esocial_dados_pagamento(self):
        """Valores do infoPgto correspondente a este holerite."""
        self.ensure_one()
        s2299 = self._esocial_s2299_declarante()
        if s2299:
            return self._esocial_dados_pagamento_rescisorio(s2299)
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

    def _esocial_motivo_desligamento(self):
        """Motivo (tabela 19) do S-2299: o da causa da rescisão, senão o do contrato.

        Com o módulo de rescisão instalado, o tipo de rescisão do holerite
        define o ``mtvDeslig`` (ex.: sem justa causa 02, acordo 33); sem tipo, ou
        sem o módulo, vale o motivo gravado no contrato.
        """
        self.ensure_one()
        if hasattr(self, "_l10n_br_motivo_desligamento_esocial"):
            codigo = self._l10n_br_motivo_desligamento_esocial()
            if codigo:
                motivo = self.env["l10n_br.esocial.motivo.desligamento"].search(
                    [("codigo", "=", codigo)], limit=1
                )
                if motivo:
                    return motivo
        return self.contract_id.l10n_br_esocial_motivo_deslig_id

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
            eventos = rescisoes.l10n_br_esocial_s2299_ids.evento_id.filtered(
                lambda evento: evento.state in EVENTO_VIGENTE
            )
            raise UserError(
                _(
                    "A rescisão selecionada está fora de vigor (estorno ou "
                    "estornada) e não vai ao eSocial. O S-2299 já gerado do "
                    "holerite estornado fica marcado como a retificar: %(como)s "
                    "e gere o S-2299 da rescisão que o substitui."
                )
                % {"como": eventos._orientacao_desfazer() or _("desfaça-o")}
            )
        if not payslips:
            raise UserError(
                _("Selecione holerites de rescisão confirmados (estado 'Feito').")
            )
        eventos = self.env["l10n_br.esocial.evento"]
        for slip in payslips:
            anterior = slip.l10n_br_esocial_s2299_ids.filtered(
                lambda s: s.evento_id.state in EVENTO_VIGENTE
            )[:1]
            if anterior:
                raise UserError(
                    _(
                        "O holerite '%(name)s' já tem S-2299 gerado (%(evento)s). "
                        "Use o evento existente; para regerar, desfaça-o antes: "
                        "%(como)s."
                    )
                    % {
                        "name": slip.number or slip.name,
                        "evento": anterior.evento_id.name,
                        "como": anterior.evento_id._orientacao_desfazer(),
                    }
                )
            retificado = slip._esocial_evento_anterior(
                "l10n_br.esocial.s2299",
                [
                    ("employee_id", "=", slip.employee_id.id),
                    ("company_id", "=", slip.company_id.id),
                    ("contract_id", "=", slip.contract_id.id),
                ],
            )
            motivo = slip._esocial_motivo_desligamento()
            if not motivo:
                raise UserError(
                    _(
                        "Informe o Motivo Desligamento eSocial no contrato de "
                        "'%(name)s' antes de gerar o S-2299."
                    )
                    % {"name": slip.employee_id.name}
                )
            vals = {
                "employee_id": slip.employee_id.id,
                "contract_id": slip.contract_id.id,
                "dt_deslig": slip.date_to,
                "motivo_desligamento_id": motivo.id,
                "payslip_id": slip.id,
                "company_id": slip.company_id.id,
            }
            if retificado:
                slip._esocial_exigir_mesmo_mes_do_s2299(retificado, vals)
                slip._esocial_exigir_sem_s1210_vigente_s2299(retificado, vals)
                # O desligamento já está no governo (S-2299 aceito da rescisão
                # estornada): o S-2299 original seria recusado. A substituta
                # entra como retificador, com o recibo do aceito.
                vals.update(
                    ind_retif="2",
                    nr_recibo=retificado.evento_id.nr_recibo,
                    evento_retificado_id=retificado.evento_id.id,
                )
            s2299 = self.env["l10n_br.esocial.s2299"].create(vals)
            eventos |= s2299.action_gerar_evento()
        return self._action_esocial_eventos(eventos)
