# Copyright 2024 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class ESocialEvento(models.Model):
    _name = "l10n_br.esocial.evento"
    _description = "eSocial - Evento"
    _inherit = ["mail.thread"]
    _order = "create_date desc"

    name = fields.Char(compute="_compute_name", store=True)
    state = fields.Selection(
        [
            ("draft", "Rascunho"),
            ("validated", "Validado"),
            ("pending", "Aguardando"),
            ("sent", "Transmitido"),
            ("success", "Sucesso"),
            ("error", "Erro"),
            ("rectified", "Retificado"),
            ("excluded", "Excluído"),
        ],
        default="draft",
        tracking=True,
        index=True,
    )
    tipo = fields.Char(
        string="Tipo Evento",
        size=10,
        required=True,
        index=True,
        help="Ex: S-1000, S-1010, S-1200, S-2200, etc.",
    )
    operacao = fields.Selection(
        [
            ("I", "Inclusão"),
            ("A", "Alteração"),
            ("E", "Exclusão"),
            ("R", "Retificação"),
        ],
        string="Operação",
        default="I",
    )
    id_evento = fields.Char(
        string="ID Evento",
        index=True,
        help="Identificador único do evento gerado pelo sistema.",
    )
    per_apur = fields.Char(
        string="Período Apuração",
        size=7,
        help="Formato AAAA-MM para eventos periódicos.",
    )
    ind_retif = fields.Selection(
        [
            ("1", "Original"),
            ("2", "Retificação"),
        ],
        string="Indicativo Retificação",
        default="1",
    )
    nr_recibo = fields.Char(
        string="Nº Recibo",
        help="Número do recibo retornado pelo governo.",
    )
    xml_envio = fields.Text(string="XML Envio")
    xml_retorno = fields.Text(string="XML Retorno")
    lote_id = fields.Many2one(
        "l10n_br.esocial.lote",
        string="Lote",
        ondelete="set null",
    )
    company_id = fields.Many2one(
        "res.company",
        string="Empresa",
        required=True,
        default=lambda self: self.env.company,
    )
    origem_model = fields.Char(
        string="Modelo Origem",
        help="Nome do modelo Odoo que originou o evento.",
    )
    origem_id = fields.Integer(
        string="ID Origem",
        help="ID do registro que originou o evento.",
    )
    avisos = fields.Text(
        string="Avisos da geração",
        compute="_compute_avisos",
        help="Avisos do registro que originou o evento (por exemplo, linhas do "
        "holerite que ficaram fora do XML por falta de configuração eSocial).",
    )
    ocorrencia_ids = fields.One2many(
        "l10n_br.esocial.ocorrencia",
        "evento_id",
        string="Ocorrências",
    )
    evento_excluido_id = fields.Many2one(
        "l10n_br.esocial.evento",
        string="Evento Excluído",
        ondelete="set null",
        help="Preenchido nos eventos S-3000: aponta o evento que a exclusão " "desfaz.",
    )
    evento_retificado_id = fields.Many2one(
        "l10n_br.esocial.evento",
        string="Evento Retificado",
        ondelete="set null",
        help="Preenchido nos retificadores (indRetif=2): aponta o evento aceito "
        "que este substitui.",
    )
    exclusao_evento_id = fields.One2many(
        "l10n_br.esocial.evento",
        "evento_excluido_id",
        string="Exclusões",
    )
    totalizador_ids = fields.One2many(
        "l10n_br.esocial.totalizador",
        "evento_id",
        string="Totalizadores",
        help="Eventos totalizadores (S-5001/S-5002/S-5011/S-5012) devolvidos "
        "pelo governo no processamento deste evento.",
    )
    totalizador_count = fields.Integer(compute="_compute_totalizador_count")

    @api.depends("origem_model", "origem_id")
    def _compute_avisos(self):
        for evento in self:
            origem = (
                self.env[evento.origem_model].browse(evento.origem_id).exists()
                if evento.origem_model in self.env
                else False
            )
            tem = origem and "avisos" in origem._fields
            evento.avisos = origem.avisos if tem else False

    @api.depends("totalizador_ids")
    def _compute_totalizador_count(self):
        for rec in self:
            rec.totalizador_count = len(rec.totalizador_ids)

    @api.depends("tipo", "id_evento")
    def _compute_name(self):
        for rec in self:
            parts = [rec.tipo or ""]
            if rec.id_evento:
                parts.append(rec.id_evento)
            rec.name = " - ".join(parts)

    def _esocial_slips_origem(self):
        """Holerites que o evento declara (pelo intermediário de origem)."""
        self.ensure_one()
        if not self.origem_model or self.origem_model not in self.env:
            return self.env["hr.payslip"]
        origem = self.env[self.origem_model].browse(self.origem_id).exists()
        if not origem or not hasattr(origem, "_esocial_slips"):
            return self.env["hr.payslip"]
        return origem._esocial_slips()

    def _s1210_dependentes(
        self,
        estados=("draft", "validated", "pending", "sent", "success"),
        manter_ides=(),
    ):
        """S-1210 (eventos) cujo pagamento aponta para o demonstrativo deste evento.

        S-1200: pagamentos ``tpPgto`` 1 ligados a ele (``s1200_id``). S-2299:
        pagamentos ``tpPgto`` 2 do trabalhador cujo ``ideDmDev`` é um dos que o
        XML do S-2299 declarou. Outros eventos não têm S-1210 dependente.
        ``manter_ides``: demonstrativos que continuam iguais (ficam de fora).
        """
        self.ensure_one()
        vazio = self.env["l10n_br.esocial.evento"]
        if self.origem_model not in ("l10n_br.esocial.s1200", "l10n_br.esocial.s2299"):
            return vazio
        origem = self.env[self.origem_model].browse(self.origem_id).exists()
        if not origem:
            return vazio
        pagamentos = self.env["l10n_br.esocial.s1210.pagamento"]
        if self.origem_model == "l10n_br.esocial.s1200":
            dominio = [("tp_pgto", "=", "1"), ("s1200_id", "=", origem.id)]
        else:
            declarados = sorted(
                origem.get_ide_dm_dev(slip) for slip in origem._slips_declarados()
            )
            dominio = [
                ("tp_pgto", "=", "2"),
                ("s1210_id.employee_id", "=", origem.employee_id.id),
                ("s1210_id.company_id", "=", origem.company_id.id),
                ("ide_dm_dev", "in", declarados),
            ]
        pagamentos = pagamentos.search(
            dominio
            + [("s1210_id.evento_id.state", "in", list(estados))]
            + ([("ide_dm_dev", "not in", list(manter_ides))] if manter_ides else [])
        )
        return pagamentos.s1210_id.evento_id

    def _orientacao_desfazer(self):
        """Como tirar o evento da frente, conforme a situação dele.

        O S-3000 só existe para evento já aceito pelo eSocial. Evento em
        rascunho ou validado nunca foi transmitido: não há o que excluir no
        governo, o caminho é apagar o evento, o que só o gestor de folha de
        pagamento pode fazer. Evento aguardando retorno ainda não tem recibo.
        """
        textos = []
        for evento in self:
            if evento.state in ("draft", "validated"):
                como = _(
                    "ainda não foi transmitido: apague o evento (só o gestor de "
                    "folha de pagamento pode apagá-lo); não use o S-3000"
                )
            elif evento.state in ("pending", "sent"):
                como = _(
                    "foi enviado e aguarda o retorno do eSocial: espere o "
                    "aceite para então excluí-lo por S-3000"
                )
            elif evento.state == "success":
                s1210s = evento._s1210_dependentes()
                if s1210s:
                    como = _(
                        "já foi aceito, mas o S-1210 %(s1210)s aponta para o "
                        "demonstrativo dele: o S-3000 só é aceito depois da "
                        "exclusão desse S-1210 (apague-o se ainda não foi "
                        "transmitido, ou exclua-o por S-3000 e espere o aceite) "
                        "e então se exclui este"
                    ) % {"s1210": ", ".join(s1210s.mapped("name"))}
                else:
                    como = _("já foi aceito: exclua-o por S-3000")
            else:
                continue
            textos.append("%s (%s)" % (evento.name, como))
        return "; ".join(textos)

    def action_validate(self):
        for rec in self:
            if rec.state != "draft":
                raise UserError(_("Apenas eventos em rascunho podem ser validados."))
            fora = rec._esocial_slips_origem().filtered("l10n_br_fora_de_vigor")
            if fora:
                raise UserError(
                    _(
                        "O evento %(nome)s declara holerite fora de vigor (estorno "
                        "ou estornado): %(slips)s. Descarte-o e gere o evento do "
                        "holerite que o substitui."
                    )
                    % {
                        "nome": rec.name,
                        "slips": ", ".join(fora.mapped(lambda s: s.number or s.name)),
                    }
                )
            rec._exigir_s2299_dos_pagamentos_rescisorios()
            rec.state = "validated"

    def _exigir_s2299_dos_pagamentos_rescisorios(self):
        """S-1210 ``tpPgto`` 2 só valida enquanto o S-2299 dele estiver vigente.

        O pagamento aponta para o ``ideDmDev`` de um S-2299. Se esse S-2299 foi
        excluído (S-3000) ou retificado por outro que não declara mais o
        demonstrativo, o S-1210 ficou órfão e o governo o recusaria.
        """
        from .intermediarios.s2299_desligamento import PREFIXO_IDE_DM_DEV

        self.ensure_one()
        if self.tipo != "S-1210" or self.origem_model != "l10n_br.esocial.s1210":
            return
        s1210 = self.env["l10n_br.esocial.s1210"].browse(self.origem_id).exists()
        for pagamento in s1210.pagamento_ids.filtered(lambda p: p.tp_pgto == "2"):
            numero = (pagamento.ide_dm_dev or "")[len(PREFIXO_IDE_DM_DEV) :]
            slip = self.env["hr.payslip"].browse(int(numero) if numero.isdigit() else 0)
            if not slip.exists() or not slip._esocial_s2299_declarante():
                raise UserError(
                    _(
                        "O pagamento de tpPgto 2 do demonstrativo %(ide)s aponta "
                        "para um S-2299 que não está mais vigente (excluído, "
                        "retificado ou sem o demonstrativo). O governo recusa o "
                        "S-1210 sem o S-2299 que o apurou: descarte este S-1210 "
                        "e gere de novo a partir do S-2299 em vigor."
                    )
                    % {"ide": pagamento.ide_dm_dev}
                )

    def action_reset_draft(self):
        for rec in self:
            if rec.state not in ("validated", "error"):
                raise UserError(
                    _("Apenas eventos validados ou com erro podem voltar a rascunho.")
                )
            rec.state = "draft"

    def registrar_aceite(self, nr_recibo=None, retorno_xml=None):
        """Registra o aceite do evento pelo eSocial.

        Concentra tudo o que depende do aceite: recibo, XML de retorno,
        totalizadores devolvidos e propagação da exclusão (S-3000). É chamado
        pelo processamento do retorno do lote.
        """
        for rec in self:
            vals = {"state": "success"}
            if nr_recibo:
                vals["nr_recibo"] = nr_recibo
            if retorno_xml:
                vals["xml_retorno"] = retorno_xml
            rec.write(vals)
            if retorno_xml:
                rec._consumir_totalizadores(retorno_xml)
            rec._propagar_exclusao()
            rec._propagar_retificacao()

    def _consumir_totalizadores(self, retorno_xml):
        """Persiste os totalizadores devolvidos no retorno deste evento."""
        self.ensure_one()
        return self.env["l10n_br.esocial.totalizador"].criar_do_retorno(
            self, retorno_xml
        )

    def _propagar_exclusao(self):
        """Marca como excluído o evento que um S-3000 aceito desfez."""
        self.ensure_one()
        if self.tipo != "S-3000" or not self.evento_excluido_id:
            return
        excluido = self.evento_excluido_id
        excluido.write({"state": "excluded"})
        excluido.message_post(
            body=_(
                "Evento excluído no eSocial pelo S-3000 %(nome)s "
                "(recibo %(recibo)s)."
            )
            % {"nome": self.name, "recibo": self.nr_recibo or _("sem recibo")}
        )

    def _propagar_retificacao(self):
        """Marca como retificado o evento que um retificador aceito substituiu."""
        self.ensure_one()
        retificado = self.evento_retificado_id
        if self.ind_retif != "2" or not retificado or retificado.state != "success":
            return
        retificado.write({"state": "rectified"})
        retificado.message_post(
            body=_("Evento retificado no eSocial por %(nome)s (recibo %(recibo)s).")
            % {"nome": self.name, "recibo": self.nr_recibo or _("sem recibo")}
        )

    def _check_audit_manager(self):
        """Only payroll managers may force an event state manually."""
        if not self.env.user.has_group("payroll.group_payroll_manager"):
            raise UserError(
                _(
                    "Apenas gestores de folha de pagamento podem forçar "
                    "manualmente o estado de um evento eSocial."
                )
            )

    def action_mark_error(self):
        self._check_audit_manager()
        for rec in self:
            rec.state = "error"
            rec.message_post(
                body=_("Estado forçado manualmente para ERRO por %(user)s.")
                % {"user": self.env.user.name}
            )
            _logger.info(
                "eSocial evento %s: estado forçado para 'error' por %s (uid=%s).",
                rec.id,
                self.env.user.name,
                self.env.uid,
            )

    def action_mark_success(self):
        self._check_audit_manager()
        for rec in self:
            rec.state = "success"
            rec.message_post(
                body=_("Estado forçado manualmente para SUCESSO por %(user)s.")
                % {"user": self.env.user.name}
            )
            rec._propagar_retificacao()
            _logger.info(
                "eSocial evento %s: estado forçado para 'success' por %s (uid=%s).",
                rec.id,
                self.env.user.name,
                self.env.uid,
            )
