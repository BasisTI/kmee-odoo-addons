# Copyright 2024 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import _, fields, models
from odoo.exceptions import UserError

# Tabela 18: acidente/doença do trabalho (01, 02) e não relacionada ao trabalho
# (03, 04). Nesses motivos a empresa paga os 15 primeiros dias e o S-2230 só é
# devido a partir daí (MOS do eSocial, S-2230; Lei 8.213/91, art. 60, § 3º).
MOTIVOS_DOENCA = frozenset({"01", "02", "03", "04"})
DIAS_EMPRESA = 15
# Novo afastamento pela mesma doença em até 60 dias do anterior soma os dias
# (Decreto 3.048/99, art. 75, § 3º).
DIAS_RECAIDA = 60


class ESocialS2230(models.Model):
    _name = "l10n_br.esocial.s2230"
    _inherit = "l10n_br.esocial.base.intermediario"
    _description = "eSocial S-2230 - Afastamento Temporário"

    employee_id = fields.Many2one(
        "hr.employee",
        string="Empregado",
        required=True,
        ondelete="cascade",
    )
    dt_ini_afast = fields.Date(
        string="Data Início Afastamento",
    )
    dt_term_afast = fields.Date(
        string="Data Término Afastamento",
    )
    cod_mot_afast = fields.Char(
        string="Código Motivo Afastamento",
        size=2,
        help="Código conforme Tabela 18 do eSocial.",
    )
    motivo_afastamento_id = fields.Many2one(
        "l10n_br.esocial.motivo.afastamento",
        string="Motivo Afastamento",
    )

    def _get_event_type(self):
        return "S-2230"

    def _afastamentos_inss_anteriores(self, inicio):
        """Afastamentos previdenciários validados do empregado antes de ``inicio``.

        Mesmo critério da TG-82: tipo com ``l10n_br_afastamento_inss``.
        """
        return (
            self.env["hr.leave"]
            .sudo()
            .search(
                [
                    ("employee_id", "=", self.employee_id.id),
                    ("state", "=", "validate"),
                    ("holiday_status_id.l10n_br_afastamento_inss", "=", True),
                    ("request_date_to", "<", inicio),
                ],
                order="request_date_to desc",
            )
        )

    def _dias_anteriores_encadeados(self, inicio):
        """Dias de afastamento anteriores a ``inicio`` ligados a ele por recaída.

        Cada afastamento anterior só entra se terminou até 60 dias antes do
        seguinte da cadeia; o 61º dia de intervalo quebra a cadeia.
        """
        total = 0
        for leave in self._afastamentos_inss_anteriores(inicio):
            if (inicio - leave.request_date_to).days > DIAS_RECAIDA:
                break
            total += (leave.request_date_to - leave.request_date_from).days + 1
            inicio = leave.request_date_from
        return total

    def _validar_afastamento_devido(self, cod_mot):
        """Recusa o S-2230 de doença/acidente que o MOS não manda informar.

        Devido só quando o afastamento, somado aos anteriores encadeados por
        recaída (até 60 dias de intervalo), passa de 15 dias. O término segue o
        início: sem o início devido, não há término a informar.
        """
        self.ensure_one()
        inicio, fim = self.dt_ini_afast, self.dt_term_afast
        if inicio and cod_mot not in MOTIVOS_DOENCA:
            return
        if not inicio:
            # Só término: o início vem do afastamento previdenciário que acaba
            # nessa data; sem ele não há como avaliar e o evento segue.
            leave = (
                self.env["hr.leave"]
                .sudo()
                .search(
                    [
                        ("employee_id", "=", self.employee_id.id),
                        ("state", "=", "validate"),
                        ("holiday_status_id.l10n_br_afastamento_inss", "=", True),
                        ("request_date_to", "=", fim),
                    ],
                    limit=1,
                )
            )
            if not leave:
                return
            inicio = leave.request_date_from
        if not fim:
            # Afastamento em aberto: o início se informa quando passar dos 15.
            return
        dias = (fim - inicio).days + 1
        anteriores = self._dias_anteriores_encadeados(inicio)
        if anteriores + dias <= DIAS_EMPRESA:
            raise UserError(
                _(
                    "Afastamento por doença/acidente de %(dias)s dia(s)%(ant)s "
                    "não gera S-2230: só é devido acima de %(lim)s dias, somando "
                    "os afastamentos pela mesma doença em até %(rec)s dias "
                    "(MOS do eSocial).",
                    dias=dias,
                    ant=(
                        _(" (mais %s dia(s) anteriores encadeados)") % anteriores
                        if anteriores
                        else ""
                    ),
                    lim=DIAS_EMPRESA,
                    rec=DIAS_RECAIDA,
                )
            )

    def _to_esociallib_dict(self):
        self.ensure_one()
        employee = self.employee_id

        cpf = employee.cnpj_cpf
        if not cpf:
            raise UserError(
                _("Empregado '%(name)s' não possui CPF configurado.")
                % {"name": employee.name}
            )
        cpf_limpo = "".join(c for c in cpf if c.isdigit())

        matricula = employee.l10n_br_esocial_matricula

        if not self.dt_ini_afast and not self.dt_term_afast:
            raise UserError(_("Informe a data de início ou término do afastamento."))

        cod_mot = self.cod_mot_afast
        if not cod_mot and self.motivo_afastamento_id:
            cod_mot = self.motivo_afastamento_id.codigo

        if self.dt_ini_afast and not cod_mot:
            raise UserError(
                _(
                    "Código do motivo de afastamento é obrigatório "
                    "ao informar início do afastamento."
                )
            )

        self._validar_afastamento_devido(cod_mot)

        ide = self._get_ide_empregador()
        proc = self._get_proc_info()

        data = {
            "tp_insc": ide["tp_insc"],
            "nr_insc": ide["nr_insc"],
            "proc_emi": proc["proc_emi"],
            "ver_proc": proc["ver_proc"],
            "cpf_trab": cpf_limpo,
        }

        if matricula:
            data["matricula"] = matricula

        if self.dt_ini_afast:
            data["dt_ini_afast"] = str(self.dt_ini_afast)
            data["cod_mot_afast"] = cod_mot

        if self.dt_term_afast:
            data["dt_term_afast"] = str(self.dt_term_afast)

        return data
