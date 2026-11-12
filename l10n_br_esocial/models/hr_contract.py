# Copyright 2024 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import fields, models


class HrContract(models.Model):
    _inherit = "hr.contract"

    l10n_br_esocial_motivo_deslig_id = fields.Many2one(
        "l10n_br.esocial.motivo.desligamento",
        string="Motivo Desligamento eSocial",
        help="Motivo do desligamento conforme Tabela 19 do eSocial.",
    )
    l10n_br_esocial_tp_jornada = fields.Selection(
        selection=[
            ("2", "2 - Jornada 12 x 36"),
            ("3", "3 - Horário diário fixo e folga variável"),
            ("4", "4 - Horário diário fixo e folga fixa (no domingo)"),
            ("5", "5 - Horário diário fixo e folga fixa (exceto no domingo)"),
            (
                "6",
                "6 - Horário diário fixo e folga fixa (em outro dia da semana), "
                "com folga adicional periódica no domingo",
            ),
            ("7", "7 - Turno ininterrupto de revezamento"),
            ("9", "9 - Demais tipos de jornada"),
        ],
        string="Tipo de Jornada eSocial",
        help="Campo tpJornada do S-2200 (leiaute S-1.3). Não há valor padrão: "
        "o evento é recusado enquanto estiver vazio.",
    )
    l10n_br_esocial_tmp_parc = fields.Selection(
        selection=[
            ("0", "0 - Não é contrato em tempo parcial"),
            ("1", "1 - Limitado a 25 horas semanais"),
            ("2", "2 - Limitado a 30 horas semanais"),
            ("3", "3 - Limitado a 26 horas semanais"),
        ],
        string="Tempo Parcial eSocial",
        default="0",
        help="Campo tmpParc do S-2200 (leiaute S-1.3).",
    )

    l10n_br_esocial_nat_atividade = fields.Selection(
        selection=[("1", "1 - Trabalho urbano"), ("2", "2 - Trabalho rural")],
        string="Natureza da Atividade eSocial",
        help="Campo natAtividade do S-2300/S-2306 (trabalhador sem vínculo). "
        "Obrigatório nas categorias 201, 202, 401, 731, 734 e 738; o eSocial "
        "não aceita nas categorias 721, 722, 771 e 901.",
    )
    l10n_br_esocial_nat_estagio = fields.Selection(
        selection=[("O", "O - Obrigatório"), ("N", "N - Não obrigatório")],
        string="Natureza do Estágio",
        help="Campo natEstagio do S-2300/S-2306 (categorias 901 e 906). Não há "
        "valor padrão: o evento é recusado enquanto estiver vazio.",
    )
    l10n_br_esocial_niv_estagio = fields.Selection(
        selection=[
            ("1", "1 - Fundamental"),
            ("2", "2 - Médio"),
            ("3", "3 - Formação profissional"),
            ("4", "4 - Superior"),
            ("8", "8 - Especial"),
            ("9", "9 - Mãe social (Lei 7.644/1987)"),
        ],
        string="Nível do Estágio",
        help="Campo nivEstagio do S-2300/S-2306. Obrigatório na categoria 901.",
    )
    l10n_br_esocial_area_atuacao = fields.Char(
        string="Área de Atuação do Estágio",
        size=100,
    )
    l10n_br_esocial_nr_apolice = fields.Char(
        string="Apólice de Seguro do Estágio",
        size=30,
    )
    l10n_br_esocial_inst_ensino_id = fields.Many2one(
        "res.partner",
        string="Instituição de Ensino",
        help="Instituição de ensino do estagiário (S-2300/S-2306). Precisa ter "
        "CNPJ: o módulo não gera o endereço de instituição estrangeira.",
    )
    l10n_br_esocial_age_integ_id = fields.Many2one(
        "res.partner",
        string="Agente de Integração",
        help="Agente de integração do estágio, quando houver (CNPJ).",
    )
    l10n_br_esocial_supervisor_id = fields.Many2one(
        "hr.employee",
        string="Supervisor do Estágio",
        help="Responsável pela supervisão do estagiário, quando informado "
        "(precisa ter CPF).",
    )
    l10n_br_esocial_dt_opc_fgts = fields.Date(
        string="Data de Opção pelo FGTS",
        help="Campo dtOpcFGTS do S-2300 (leiaute S-1.3). Obrigatório na "
        "categoria 721 (diretor não empregado, com FGTS).",
    )

    l10n_br_esocial_cnpj_oper_saude = fields.Char(
        string="CNPJ da Operadora do Plano de Saúde",
        size=18,
        help="Operadora do plano privado coletivo empresarial (S-1210, "
        "planSaude/cnpjOper). Obrigatório quando o holerite tem desconto de "
        "plano de saúde (rubrica com incidência IRRF 67 ou 9067).",
    )
    l10n_br_esocial_reg_ans = fields.Char(
        string="Registro na ANS",
        size=6,
        help="Registro da operadora na ANS (S-1210, planSaude/regANS).",
    )
    l10n_br_esocial_cnpj_prev_compl = fields.Char(
        string="CNPJ da Entidade de Previdência Complementar",
        size=18,
        help="Entidade (S-1210, previdCompl/cnpjEntidPC). Obrigatório quando "
        "o holerite tem desconto de previdência complementar (rubrica com "
        "incidência IRRF 46-48 ou 61-66).",
    )
