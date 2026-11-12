# Copyright 2026 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import fields, models


class HrEmployeeRelative(models.Model):
    """Parente do empregado, com os dados do dependente do S-2200.

    Só entra no evento (grupo ``dependente``) o parente que tem o tipo de
    dependente eSocial preenchido; os demais continuam sendo só contato.
    """

    _inherit = "hr.employee.relative"

    l10n_br_esocial_tp_dep_id = fields.Many2one(
        "l10n_br.esocial.tipo.dependente",
        string="Tipo de Dependente eSocial",
        domain=[("dt_fim", "=", False)],
        help="Tabela 07 do eSocial. Preencha para declarar o parente como "
        "dependente no S-2200; vazio = não é declarado.",
    )
    l10n_br_esocial_cpf = fields.Char(
        string="CPF do Dependente",
        size=14,
    )
    l10n_br_esocial_dep_irrf = fields.Boolean(
        string="Dependente para IRRF",
        help="Dedução do rendimento tributável pelo Imposto de Renda (depIRRF). "
        "Exige o CPF.",
    )
    l10n_br_esocial_dep_sf = fields.Boolean(
        string="Dependente para Salário-Família",
        help="Recebimento do salário-família (depSF).",
    )
    l10n_br_esocial_inc_trab = fields.Boolean(
        string="Incapaz para o Trabalho",
        help="Incapacidade física ou mental para o trabalho (incTrab).",
    )
    l10n_br_esocial_descr_dep = fields.Char(
        string="Descrição da Dependência",
        size=100,
        help="Obrigatória quando o tipo de dependente é 99 - Agregado/Outros.",
    )
