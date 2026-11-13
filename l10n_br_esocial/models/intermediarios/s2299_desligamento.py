# Copyright 2024 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import logging

from dateutil.relativedelta import relativedelta

from odoo import _, fields, models
from odoo.exceptions import UserError

from .s1200_remuneracao import CATEGORIAS_DECLARAVEIS

_logger = logging.getLogger(__name__)


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

    avisos = fields.Text(
        string="Avisos da geração",
        readonly=True,
        copy=False,
        help="Regras da rescisão com valor e sem código ou natureza de rubrica "
        "eSocial: ficam fora das verbas rescisórias do S-2299.",
    )

    def get_ide_dm_dev(self):
        """Identificador do demonstrativo das verbas rescisórias (ideDmDev).

        O S-1210 de tpPgto 2 aponta para este mesmo identificador; por isso
        sai do id do registro, como no S-1200.
        """
        self.ensure_one()
        return "DEM%06d" % (self.id or 1)

    def _build_verbas_resc(self):
        """``verbasResc`` do holerite de rescisão: uma ``detVerbas`` por rubrica.

        Entram as linhas com valor, código e natureza de rubrica eSocial, o que
        inclui a verba de aviso prévio indenizado e os reflexos (13º, férias,
        FGTS da rescisão). Linha com valor e sem configuração fica fora e é
        avisada no campo ``avisos``.
        """
        self.ensure_one()
        slip = self.payslip_id
        if not slip:
            self.avisos = False
            return []
        itens = []
        sem_config = {}
        for line in slip.line_ids:
            rule = line.salary_rule_id
            if not line.total:
                continue
            if (
                not rule.l10n_br_esocial_nat_rubr_id
                or not rule.l10n_br_esocial_cod_rubr
            ):
                if rule.category_id.code in CATEGORIAS_DECLARAVEIS:
                    sem_config.setdefault(rule, []).append(line.total)
                continue
            itens.append(
                {
                    "cod_rubr": rule.l10n_br_esocial_cod_rubr,
                    "ide_tab_rubr": rule.l10n_br_esocial_ide_tab_rubr or "1",
                    "vr_rubr": str(abs(line.total)),
                }
            )
        if sem_config:
            linhas = []
            for regra in sem_config:
                linhas.append(
                    _(
                        "Regra '%(regra)s' (%(code)s) com valor na rescisão e sem "
                        "código ou natureza de rubrica eSocial: fora do S-2299."
                    )
                    % {"regra": regra.name, "code": regra.code}
                )
            self.avisos = "\n".join(linhas)
            _logger.warning("eSocial S-2299 %s: %s", self.id, self.avisos)
        else:
            self.avisos = False
        if not itens:
            return []
        company = self.company_id
        cnpj_estab = "".join(c for c in (company.partner_id.vat or "") if c.isdigit())
        return [
            {
                "ide_dm_dev": self.get_ide_dm_dev(),
                "info_per_apur": {
                    "ide_estab_lot": [
                        {
                            "tp_insc": 1,
                            "nr_insc": cnpj_estab,
                            "cod_lotacao": company.l10n_br_esocial_cod_lotacao or "1",
                            "det_verbas": itens,
                        }
                    ],
                },
            }
        ]

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

        verbas_resc = self._build_verbas_resc()
        if verbas_resc:
            data["verbas_resc"] = verbas_resc

        return data
