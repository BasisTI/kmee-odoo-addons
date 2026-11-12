# Copyright 2026 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from datetime import timedelta

from odoo import _, fields, models

from .tsv_mixin import DIAS_TERMINO_FUTURO

# Categorias do S-2399 que exigem informação própria (leiaute S-1.3).
CATEGORIAS_MOTIVO = ("721",)
CATEGORIAS_PENSAO = ("201", "202", "721")
DT_PENSAO_OBRIGATORIA = "2019-04-21"


class ESocialS2399(models.Model):
    _name = "l10n_br.esocial.s2399"
    _inherit = "l10n_br.esocial.tsv.mixin"
    _description = "eSocial S-2399 - Trabalhador sem vínculo - Término"

    dt_term = fields.Date(string="Data do Término", required=True)
    mtv_deslig_tsv = fields.Selection(
        [
            ("01", "01 - Exoneração do diretor sem justa causa"),
            ("02", "02 - Término de mandato do diretor não reconduzido"),
            ("03", "03 - Exoneração a pedido do diretor"),
            ("04", "04 - Exoneração do diretor por culpa recíproca ou força maior"),
            ("05", "05 - Morte do diretor"),
            ("06", "06 - Exoneração do diretor por falência ou encerramento"),
            ("99", "99 - Outros"),
        ],
        string="Motivo do Término",
        help="Campo mtvDesligTSV do S-2399 (leiaute S-1.3): obrigatório para a "
        "categoria 721 (diretor não empregado) e proibido nas demais. O motivo 07 "
        "(mudança de CPF) não é gerado por este módulo.",
    )
    pens_alim = fields.Selection(
        [
            ("0", "0 - Não existe pensão alimentícia"),
            ("1", "1 - Percentual de pensão alimentícia"),
            ("2", "2 - Valor de pensão alimentícia"),
            ("3", "3 - Percentual e valor de pensão alimentícia"),
        ],
        string="Pensão Alimentícia",
        help="Obrigatório para as categorias 201, 202 e 721; proibido nas demais.",
    )
    perc_aliment = fields.Float(string="Percentual da Pensão", digits=(5, 2))
    vr_alim = fields.Float(string="Valor da Pensão", digits=(14, 2))

    def _get_event_type(self):
        return "S-2399"

    def _get_dt_term(self, contract, employee):
        nome = contract.display_name
        if contract.date_start and self.dt_term < contract.date_start:
            self._erro_cadastro(
                _(
                    "Contrato '%(name)s': o término (%(dt)s) é anterior ao início "
                    "do contrato."
                ),
                name=nome,
                dt=self.dt_term,
            )
        limite = fields.Date.context_today(self) + timedelta(days=DIAS_TERMINO_FUTURO)
        if self.dt_term > limite:
            self._erro_cadastro(
                _(
                    "Contrato '%(name)s': o término (%(dt)s) passa de %(dias)s "
                    "dias à frente da data atual."
                ),
                name=nome,
                dt=self.dt_term,
                dias=DIAS_TERMINO_FUTURO,
            )
        return str(self.dt_term)

    def _get_info_termino(self, categoria, employee):
        """Motivo e pensão alimentícia, conforme a categoria."""
        codigo = categoria.codigo
        info = {}
        nome = employee.name
        if codigo in CATEGORIAS_MOTIVO:
            if not self.mtv_deslig_tsv:
                self._erro_cadastro(
                    _(
                        "Trabalhador '%(name)s': a categoria %(cat)s exige o Motivo do Término."
                    ),
                    name=nome,
                    cat=codigo,
                )
            info["mtv_deslig_tsv"] = self.mtv_deslig_tsv
        elif self.mtv_deslig_tsv:
            self._erro_cadastro(
                _(
                    "Trabalhador '%(name)s': o Motivo do Término só vale para a "
                    "categoria 721; a categoria %(cat)s não o informa."
                ),
                name=nome,
                cat=codigo,
            )
        if codigo in CATEGORIAS_PENSAO:
            # Obrigatória com término depois de 21/04/2019; opcional até essa data.
            if str(self.dt_term) > DT_PENSAO_OBRIGATORIA and not self.pens_alim:
                self._erro_cadastro(
                    _(
                        "Trabalhador '%(name)s': a categoria %(cat)s exige informar "
                        "a Pensão Alimentícia."
                    ),
                    name=nome,
                    cat=codigo,
                )
        elif self.pens_alim:
            self._erro_cadastro(
                _(
                    "Trabalhador '%(name)s': a Pensão Alimentícia não se informa "
                    "na categoria %(cat)s."
                ),
                name=nome,
                cat=codigo,
            )
        if self.pens_alim:
            info["pens_alim"] = int(self.pens_alim)
            if self.pens_alim in ("1", "3"):
                if not 0 < self.perc_aliment <= 100:
                    self._erro_cadastro(
                        _(
                            "Trabalhador '%(name)s': o percentual da pensão "
                            "deve ficar entre 0 e 100."
                        ),
                        name=nome,
                    )
                info["perc_aliment"] = "%.2f" % self.perc_aliment
            if self.pens_alim in ("2", "3"):
                if self.vr_alim <= 0:
                    self._erro_cadastro(
                        _(
                            "Trabalhador '%(name)s': o valor da pensão deve ser maior que zero."
                        ),
                        name=nome,
                    )
                info["vr_alim"] = "%.2f" % self.vr_alim
        return info

    def _to_esociallib_dict(self):
        """Dict do S-2399, ou ``UserError`` com TODOS os dados que faltam."""
        self.ensure_one()
        employee = self.employee_id
        contract = self.contract_id
        erros = []
        cpf, matricula, categoria, ide = self._identificar(erros, "S-2399")
        proc = self._get_proc_info()
        dt_term = self._coletar(erros, self._get_dt_term, contract, employee)
        termino = (
            self._coletar(erros, self._get_info_termino, categoria, employee)
            if categoria
            else {}
        )
        if erros:
            self._erro_evento("S-2399", erros)
        data = {
            "tp_insc": ide["tp_insc"],
            "nr_insc": ide["nr_insc"],
            "proc_emi": proc["proc_emi"],
            "ver_proc": proc["ver_proc"],
            "cpf_trab": cpf,
            "matricula": matricula,
            # Sem codCateg: ver S-2306 (exclusivo com a matrícula).
            "dt_term": dt_term,
        }
        data.update(termino)
        return data

    def _gerar_xml(self):
        return self._montar_xml()
