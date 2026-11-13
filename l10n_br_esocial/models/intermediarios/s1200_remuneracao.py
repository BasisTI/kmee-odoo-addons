# Copyright 2024 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import logging

from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

# Categorias de regra que carregam verba ou desconto do trabalhador. Totais
# (GROSS, NET), informativas, encargos do empregador e provisões não são
# rubricas do S-1200 e não geram aviso.
CATEGORIAS_DECLARAVEIS = ("BASIC", "ALW", "DED", "PROV_INDENIZ", "PROV_TRIB_IRRF")
# Regras que o holerite calcula mas que não são verba paga ao trabalhador: a
# multa do FGTS vai à conta vinculada (FGTS Digital), não ao líquido, e não tem
# natureza de rubrica no leiaute (a 6101 é a indenização paga ao empregado).
CODIGOS_FORA_DAS_VERBAS = ("MULTA_FGTS",)


class ESocialS1200(models.Model):
    _name = "l10n_br.esocial.s1200"
    _inherit = "l10n_br.esocial.base.intermediario"
    _description = "eSocial S-1200 - Remuneração do Trabalhador"

    employee_id = fields.Many2one(
        "hr.employee",
        string="Empregado",
        required=True,
        ondelete="cascade",
    )
    payslip_ids = fields.Many2many(
        "hr.payslip",
        string="Holerites",
    )
    per_apur = fields.Char(
        string="Período Apuração",
        size=7,
        required=True,
        help="Formato AAAA-MM para mensal ou AAAA para 13º.",
    )
    ind_apuracao = fields.Selection(
        [
            ("1", "Mensal"),
            ("2", "Anual (13º Salário)"),
        ],
        string="Tipo Apuração",
        default="1",
        required=True,
    )
    ind_retif = fields.Selection(
        [
            ("1", "Original"),
            ("2", "Retificação"),
        ],
        string="Indicativo Retificação",
        default="1",
        required=True,
    )
    nr_recibo = fields.Char(
        string="Nº Recibo",
        help="Número do recibo do evento a ser retificado. "
        "Obrigatório quando Indicativo de Retificação for 'Retificação'.",
    )

    evento_retificado_id = fields.Many2one(
        "l10n_br.esocial.evento",
        string="Evento Retificado",
        readonly=True,
        copy=False,
        help="Evento aceito que este retificador substitui. Quando o "
        "retificador é aceito, o evento retificado passa a 'Retificado'.",
    )

    avisos = fields.Text(
        string="Avisos da geração",
        readonly=True,
        copy=False,
        help="Linhas do holerite que ficaram fora do XML por falta de "
        "configuração eSocial na regra salarial.",
    )

    @api.constrains("nr_recibo")
    def _check_nr_recibo(self):
        for rec in self:
            rec._validar_nr_recibo(rec.nr_recibo, _("Nº Recibo"))

    def _get_event_type(self):
        return "S-1200"

    def _esocial_slips(self):
        return self.payslip_ids

    def get_ide_dm_dev(self):
        """Identificador do demonstrativo de valores devidos (ideDmDev).

        O S-1210 tem de apontar para o MESMO ideDmDev informado no S-1200 da
        competência (é assim que o governo liga o pagamento à apuração), por
        isso o identificador é derivado do id do registro e nunca do contexto
        de geração.
        """
        self.ensure_one()
        return "DEM%06d" % (self.id or 1)

    def _prepare_evento_vals(self, xml, id_evento):
        vals = super()._prepare_evento_vals(xml, id_evento)
        # nr_recibo do evento guarda o recibo DEVOLVIDO pelo governo, não o
        # recibo retificado — este último vive no intermediário.
        vals.update(
            {
                "per_apur": self.per_apur,
                "ind_retif": self.ind_retif,
                "operacao": "R" if self.ind_retif == "2" else "I",
                "evento_retificado_id": self.evento_retificado_id.id,
            }
        )
        return vals

    def _build_itens_remun(self):
        """Build list of rubric items from payslip lines."""
        itens = []
        sem_config = {}
        for payslip in self.payslip_ids:
            payslip._esocial_exigir_rubrica_maternidade()
            for line in payslip.line_ids:
                rule = line.salary_rule_id
                # Skip zero-valued lines — they must not be reported.
                if not line.total:
                    continue
                # Only lines with nat_rubr go to XML (ABGF rule), mas a regra
                # com valor e sem configuração é avisada, não calada.
                if (
                    not rule.l10n_br_esocial_nat_rubr_id
                    or not rule.l10n_br_esocial_cod_rubr
                ):
                    if (
                        rule.category_id.code in CATEGORIAS_DECLARAVEIS
                        and rule.code not in CODIGOS_FORA_DAS_VERBAS
                    ):
                        sem_config.setdefault(rule, []).append(line.total)
                    continue
                valor = abs(line.total)
                if valor:
                    itens.append(self._item_remun(rule, valor))
        self._registrar_avisos_sem_config(sem_config)
        return itens

    def _exige_ind_apur_ir(self):
        """``indApurIR`` é obrigatório a partir de 07/2021 (mensal) ou 2021 (13º)."""
        return self.per_apur >= ("2021-07" if self.ind_apuracao == "1" else "2021")

    def _item_remun(self, rule, valor):
        item = {
            "cod_rubr": rule.l10n_br_esocial_cod_rubr,
            "ide_tab_rubr": rule.l10n_br_esocial_ide_tab_rubr or "1",
            "vr_rubr": str(valor),
        }
        if self._exige_ind_apur_ir():
            # 0 = apuração normal, sob a folha declarada no eSocial.
            item["ind_apur_ir"] = 0
        return item

    def _gerar_xml(self):
        xml = super()._gerar_xml()
        categoria = self.employee_id.l10n_br_esocial_categoria_id.codigo
        if not self._categoria_rgps(categoria):
            return xml
        contrato = self.employee_id.contract_id
        if self.ind_apuracao == "1":
            ano, mes = (int(x) for x in self.per_apur.split("-"))
            inicio = fields.Date.to_date("%04d-%02d-01" % (ano, mes))
        else:
            inicio = fields.Date.to_date("%s-12-01" % self.per_apur)
        fim = inicio + relativedelta(months=1, days=-1)
        grau = self._grau_exp(contrato, inicio, fim)
        return self._xml_com_info_ag_nocivo(xml, "S-1200", "remunPerApur", grau)

    def _registrar_avisos_sem_config(self, sem_config):
        """Avisa (log e campo ``avisos``) das regras que ficaram fora do XML."""
        if not sem_config:
            self.avisos = False
            return
        linhas = []
        for rule, valores in sem_config.items():
            faltando = []
            if not rule.l10n_br_esocial_cod_rubr:
                faltando.append(_("código da rubrica"))
            if not rule.l10n_br_esocial_nat_rubr_id:
                faltando.append(_("natureza da rubrica"))
            linhas.append(
                _(
                    "Regra '%(regra)s' (%(code)s) com valor no holerite e sem "
                    "%(faltando)s eSocial: %(n)d linha(s), total %(total).2f, "
                    "fora do S-1200."
                )
                % {
                    "regra": rule.name,
                    "code": rule.code,
                    "faltando": " e ".join(faltando),
                    "n": len(valores),
                    "total": sum(abs(v) for v in valores),
                }
            )
        self.avisos = "\n".join(linhas)
        _logger.warning(
            "eSocial S-1200 %s (%s): %s", self.id, self.per_apur, self.avisos
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
        if not matricula:
            raise UserError(
                _("Empregado '%(name)s' não possui Matrícula eSocial configurada.")
                % {"name": employee.name}
            )
        categoria = employee.l10n_br_esocial_categoria_id
        if not categoria:
            raise UserError(
                _("Empregado '%(name)s' não possui Categoria Trabalhador eSocial.")
                % {"name": employee.name}
            )

        itens = self._build_itens_remun()
        if not itens:
            raise UserError(
                _(
                    "Nenhuma linha de holerite com Natureza de Rubrica eSocial "
                    "preenchida. Configure os campos eSocial nas regras salariais."
                )
            )

        ide = self._get_ide_empregador()
        proc = self._get_proc_info()
        company = self.company_id

        # Build establishment CNPJ
        cnpj_estab = "".join(c for c in (company.partner_id.vat or "") if c.isdigit())

        cod_lotacao = company.l10n_br_esocial_cod_lotacao or "1"

        ind_retif = int(self.ind_retif)
        if ind_retif == 2 and not self.nr_recibo:
            raise UserError(
                _(
                    "Retificação (ind_retif=2) exige o Nº do Recibo do evento "
                    "original a ser retificado."
                )
            )

        data = {
            "tp_insc": ide["tp_insc"],
            "nr_insc": ide["nr_insc"],
            "cpf_trab": cpf_limpo,
            "ind_apuracao": int(self.ind_apuracao),
            "per_apur": self.per_apur,
            "ind_retif": ind_retif,
            "proc_emi": proc["proc_emi"],
            "ver_proc": proc["ver_proc"],
            "dm_dev": [
                {
                    "ide_dm_dev": self.get_ide_dm_dev(),
                    "cod_categ": categoria.codigo,
                    "info_per_apur": {
                        "ide_estab_lot": [
                            {
                                "tp_insc": 1,
                                "nr_insc": cnpj_estab,
                                "cod_lotacao": cod_lotacao,
                                "remun_per_apur": [
                                    {
                                        "matricula": matricula,
                                        "itens_remun": itens,
                                    }
                                ],
                            }
                        ],
                    },
                }
            ],
        }

        if ind_retif == 2:
            data["nr_recibo"] = self.nr_recibo

        return data
