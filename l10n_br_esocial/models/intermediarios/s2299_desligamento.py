# Copyright 2024 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from dateutil.relativedelta import relativedelta

from odoo import _, fields, models
from odoo.exceptions import UserError


class ESocialS2299(models.Model):
    _name = "l10n_br.esocial.s2299"
    _inherit = "l10n_br.esocial.base.intermediario"
    _description = "eSocial S-2299 - Desligamento"

    employee_id = fields.Many2one(
        "hr.employee",
        string="Empregado",
        required=True,
        ondelete="cascade",
    )
    contract_id = fields.Many2one(
        "hr.contract",
        string="Contrato",
        required=True,
        ondelete="cascade",
    )
    dt_deslig = fields.Date(
        string="Data do Desligamento",
        required=True,
    )
    motivo_desligamento_id = fields.Many2one(
        "l10n_br.esocial.motivo.desligamento",
        string="Motivo Desligamento",
        required=True,
    )
    payslip_id = fields.Many2one(
        "hr.payslip",
        string="Holerite de Rescisão",
        ondelete="set null",
        help="Holerite da rescisão. Com o módulo de rescisão instalado, o "
        "aviso prévio (indenizado ou não) e a data projetada do seu término "
        "saem daqui e prevalecem sobre os campos abaixo.",
    )
    ind_pagto_api = fields.Selection(
        [
            ("S", "Sim"),
            ("N", "Não"),
        ],
        string="Aviso Prévio Indenizado",
        default="N",
        help="indPagtoAPI: o empregador pagou aviso prévio indenizado ao "
        "empregado. Só é 'Sim' quando há a verba de aviso indenizado (dispensa "
        "sem justa causa ou acordo, com aviso marcado como indenizado); aviso "
        "trabalhado, pedido de demissão e justa causa são 'Não'.",
    )
    dt_proj_fim_api = fields.Date(
        string="Data Projetada Fim Aviso Prévio",
        help="dtProjFimAPI: obrigatória com aviso indenizado, igual ou "
        "posterior à data do desligamento.",
    )

    def _aviso_indenizado(self):
        """``(indPagtoAPI, dtProjFimAPI)`` do desligamento.

        Com o holerite de rescisão, vale a regra da folha
        (``_l10n_br_aviso_indenizado_devido``) e a data projetada é o
        desligamento mais os dias de aviso (Lei 12.506/2011); sem ele, vale o
        que foi informado no evento.
        """
        self.ensure_one()
        slip = self.payslip_id
        if slip and hasattr(slip, "_l10n_br_aviso_indenizado_devido"):
            if slip._l10n_br_aviso_indenizado_devido():
                dias = slip._l10n_br_dias_aviso_previo()
                return "S", self.dt_deslig + relativedelta(days=dias)
            return "N", False
        return self.ind_pagto_api or "N", self.dt_proj_fim_api

    def _get_event_type(self):
        return "S-2299"

    def _esocial_slips(self):
        return self.payslip_id

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
        if not matricula:
            raise UserError(
                _("Empregado '%(name)s' não possui Matrícula eSocial.")
                % {"name": employee.name}
            )

        categoria = employee.l10n_br_esocial_categoria_id
        if categoria:
            self._validar_categoria_evento(employee, categoria, "S-2299")

        ide = self._get_ide_empregador()
        proc = self._get_proc_info()

        ind_pagto_api, dt_proj_fim_api = self._aviso_indenizado()
        if ind_pagto_api == "S":
            if not dt_proj_fim_api:
                raise UserError(
                    _(
                        "S-2299 de '%(name)s': com aviso prévio indenizado "
                        "(indPagtoAPI = S) informe a Data Projetada Fim Aviso "
                        "Prévio."
                    )
                    % {"name": employee.name}
                )
            if dt_proj_fim_api < self.dt_deslig:
                raise UserError(
                    _(
                        "S-2299 de '%(name)s': a data projetada do fim do aviso "
                        "(%(proj)s) não pode ser anterior ao desligamento "
                        "(%(deslig)s)."
                    )
                    % {
                        "name": employee.name,
                        "proj": dt_proj_fim_api,
                        "deslig": self.dt_deslig,
                    }
                )

        data = {
            "tp_insc": ide["tp_insc"],
            "nr_insc": ide["nr_insc"],
            "proc_emi": proc["proc_emi"],
            "ver_proc": proc["ver_proc"],
            "cpf_trab": cpf_limpo,
            "matricula": matricula,
            "mtv_deslig": self.motivo_desligamento_id.codigo,
            "dt_deslig": str(self.dt_deslig),
            "ind_pagto_api": ind_pagto_api,
        }

        if ind_pagto_api == "S":
            data["dt_proj_fim_api"] = str(dt_proj_fim_api)

        return data
