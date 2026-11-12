# Copyright 2024 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import logging
from collections import OrderedDict

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)

try:
    from erpbrasil.base.fiscal import cnpj_cpf
except ImportError:  # pragma: no cover
    cnpj_cpf = None

try:
    from esociallib.generator import _BUILDERS, _ensure_builders_loaded
    from esociallib.validators import validate_xsd
except ImportError:  # pragma: no cover
    _BUILDERS = {}
    _ensure_builders_loaded = None
    validate_xsd = None

# Domínio de tpPgto do leiaute S-1.3 (evtPgtos.xsd, pacote 2026-10-26): o
# código indica o evento que apurou o demonstrativo pago.
TP_PGTO = [
    ("1", "1 - Remuneração apurada no S-1200"),
    ("2", "2 - Verbas rescisórias apuradas no S-2299"),
    ("3", "3 - Verbas rescisórias apuradas no S-2399"),
    ("4", "4 - Remuneração apurada no S-1202"),
    ("5", "5 - Benefícios previdenciários apurados no S-1207"),
]

# Incidência IRRF (codIncIRRF do S-1010) que obriga cada grupo de infoIRComplem
# quando a rubrica é um desconto (tpRubr 2): condição dos grupos no leiaute S-1.3.
COD_IRRF_PLANO_SAUDE = ("67", "9067")
COD_IRRF_PENSAO = ("51", "52", "53", "54")
COD_IRRF_PREV_PRIVADA = ("46", "47", "48")
COD_IRRF_PREV_FAPI = ("61", "62", "66")
COD_IRRF_PREV_FUNPRESP = ("63", "64", "65")
COD_IRRF_PREV_COMPL = (
    COD_IRRF_PREV_PRIVADA + COD_IRRF_PREV_FAPI + COD_IRRF_PREV_FUNPRESP
)
NAT_RUBR_PLANO_SAUDE = "9219"

# Código de receita (TS_CR_IR) do IRRF retido, por categoria do trabalhador.
TP_CR_PADRAO = "056107"  # trabalho assalariado (mensal, 13º e férias)
TP_CR_DOMESTICO = "056108"
TP_CR_SEM_VINCULO = "058806"


class ESocialS1210(models.Model):
    _name = "l10n_br.esocial.s1210"
    _inherit = "l10n_br.esocial.base.intermediario"
    _description = "eSocial S-1210 - Pagamentos de Rendimentos do Trabalho"
    _order = "per_apur desc, id desc"

    name = fields.Char(compute="_compute_name", store=True)
    employee_id = fields.Many2one(
        "hr.employee",
        string="Beneficiário",
        required=True,
        ondelete="cascade",
    )
    per_apur = fields.Char(
        string="Período Apuração",
        size=7,
        required=True,
        help="Competência do PAGAMENTO (regime de caixa), formato AAAA-MM. "
        "Não confundir com a competência da folha, que vai em cada "
        "demonstrativo no campo Período de Referência.",
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
        string="Nº Recibo Retificado",
        help="Recibo do S-1210 a ser retificado. Obrigatório quando o "
        "Indicativo de Retificação for 'Retificação'.",
    )
    pagamento_ids = fields.One2many(
        "l10n_br.esocial.s1210.pagamento",
        "s1210_id",
        string="Pagamentos",
    )
    vr_liq_total = fields.Monetary(
        string="Total Líquido Pago",
        compute="_compute_vr_liq_total",
        store=True,
        currency_field="currency_id",
    )
    currency_id = fields.Many2one(
        "res.currency",
        related="company_id.currency_id",
        readonly=True,
    )

    @api.depends("employee_id", "per_apur")
    def _compute_name(self):
        for rec in self:
            rec.name = " - ".join(
                parte for parte in (rec.employee_id.name, rec.per_apur) if parte
            )

    @api.depends("pagamento_ids.vr_liq")
    def _compute_vr_liq_total(self):
        for rec in self:
            rec.vr_liq_total = sum(rec.pagamento_ids.mapped("vr_liq"))

    @api.constrains("per_apur")
    def _check_per_apur(self):
        for rec in self:
            rec._validar_competencia(rec.per_apur, _("Período Apuração"))

    @api.constrains("nr_recibo")
    def _check_nr_recibo(self):
        for rec in self:
            rec._validar_nr_recibo(rec.nr_recibo, _("Nº Recibo Retificado"))

    def _get_event_type(self):
        return "S-1210"

    def _prepare_evento_vals(self, xml, id_evento):
        vals = super()._prepare_evento_vals(xml, id_evento)
        vals.update(
            {
                "per_apur": self.per_apur,
                "ind_retif": self.ind_retif,
                "operacao": "R" if self.ind_retif == "2" else "I",
            }
        )
        return vals

    def _to_esociallib_dict(self):
        self.ensure_one()
        employee = self.employee_id

        cpf = employee.cnpj_cpf
        if not cpf:
            raise UserError(
                _("Beneficiário '%(name)s' não possui CPF configurado.")
                % {"name": employee.name}
            )

        if not self.pagamento_ids:
            raise UserError(
                _(
                    "S-1210 de %(name)s (%(per)s) não possui pagamentos. O "
                    "evento informa pagamentos efetivamente realizados: gere-o "
                    "a partir dos holerites pagos."
                )
                % {"name": employee.name, "per": self.per_apur}
            )

        ind_retif = int(self.ind_retif)
        if ind_retif == 2 and not self.nr_recibo:
            raise UserError(
                _(
                    "Retificação (ind_retif=2) exige o Nº do Recibo do S-1210 "
                    "original a ser retificado."
                )
            )

        ide = self._get_ide_empregador()
        proc = self._get_proc_info()

        data = {
            "tp_insc": ide["tp_insc"],
            "nr_insc": ide["nr_insc"],
            "per_apur": self.per_apur,
            "ind_retif": ind_retif,
            "proc_emi": proc["proc_emi"],
            "ver_proc": proc["ver_proc"],
            "cpf_benef": self._so_digitos(cpf),
            "info_pgto": [
                pagamento._to_esociallib_dict()
                for pagamento in self.pagamento_ids.sorted("dt_pgto")
            ],
        }
        if ind_retif == 2:
            data["nr_recibo"] = self.nr_recibo
        return data

    # ── infoIRComplem: informações que alimentam a DIRF/informe ────────────
    # A esociallib 0.1.3 monta o infoIRComplem com nomes do leiaute antigo
    # (descDep, cnpjEntPrevid, vlrDedPrevid, planSaude/infoDep, sem dedDepen
    # nem tpRend): o módulo o gera conforme o evtPgtos.xsd do S-1.3.

    def _tp_cr(self):
        categoria = self.employee_id.l10n_br_esocial_categoria_id.codigo or ""
        if categoria == "104":
            return TP_CR_DOMESTICO
        if categoria[:1] == "7":
            return TP_CR_SEM_VINCULO
        return TP_CR_PADRAO

    @staticmethod
    def _linhas_desconto(payslip, codigos=(), natureza=None):
        """Descontos (tpRubr 2) do holerite com a incidência IRRF dada."""
        linhas = payslip.line_ids.filtered(
            lambda linha: linha.salary_rule_id.l10n_br_esocial_tp_rubr == "2"
            and (
                linha.salary_rule_id.l10n_br_esocial_cod_inc_irrf in codigos
                or (
                    natureza
                    and linha.salary_rule_id.l10n_br_esocial_nat_rubr_id.codigo
                    == natureza
                )
            )
        )
        return linhas

    def _parentes_ir(self, erros):
        """Parentes do empregado que entram no complemento de IR."""
        employee = self.employee_id
        parentes = employee.relative_ids
        pensao = parentes.filtered("l10n_br_esocial_pensao_alimenticia")
        if len(pensao) > 1:
            erros.append(
                _(
                    "'%(name)s' tem %(n)s beneficiários da pensão alimentícia "
                    "marcados, mas a folha desconta um valor único: o S-1210 "
                    "não tem como repartir. Deixe um só."
                )
                % {"name": employee.name, "n": len(pensao)}
            )
        return parentes, pensao

    def _cpf_parente(self, rel, finalidade, erros):
        cpf = self._so_digitos(rel.l10n_br_esocial_cpf)
        if len(cpf) != 11 or (cnpj_cpf and not cnpj_cpf.validar(cpf)):
            erros.append(
                _(
                    "Parente '%(dep)s' de '%(name)s' (%(fim)s): informe um CPF "
                    "válido no cadastro do parente."
                )
                % {
                    "dep": rel.name,
                    "name": self.employee_id.name,
                    "fim": finalidade,
                }
            )
            return None
        return cpf

    def _cnpj_contrato(self, contrato, campo, rotulo, erros):
        cnpj = self._so_digitos(contrato[campo])
        if len(cnpj) != 14 or (cnpj_cpf and not cnpj_cpf.validar(cnpj)):
            erros.append(
                _(
                    "Contrato de '%(name)s': informe um CNPJ válido em "
                    "'%(rotulo)s' (o holerite tem o desconto correspondente)."
                )
                % {"name": self.employee_id.name, "rotulo": rotulo}
            )
            return None
        return cnpj

    @staticmethod
    def _tp_rend(pagamento):
        """11 = remuneração mensal; 12 = 13º salário (competência anual)."""
        return "12" if len(pagamento.per_ref or "") == 4 else "11"

    def _ir_dependentes(self, pagamento, slip, dedutivel, acc):
        """Dedução do rendimento por dependente declarado para IRRF."""
        employee = self.employee_id
        erros = acc["erros"]
        if not (dedutivel and slip.line_ids.filtered(lambda ln: ln.code == "IRRF")):
            return
        folha = employee.l10n_br_irrf_dependentes
        if folha != len(dedutivel):
            erros.append(
                _(
                    "'%(name)s': a folha deduz %(folha)s dependente(s) no IRRF, "
                    "mas o cadastro declara %(dep)s para IRRF (parentes com tipo "
                    "eSocial e 'Dependente para IRRF'). Acerte um dos dois antes "
                    "de gerar o S-1210."
                )
                % {"name": employee.name, "folha": folha, "dep": len(dedutivel)}
            )
            return
        valor = self.env["l10n_br.hr.payroll.irrf.dependente"]._valor(slip.date_to)
        for rel in dedutivel:
            cpf = self._cpf_parente(rel, _("dependente para IRRF"), erros)
            if cpf:
                chave = (self._tp_rend(pagamento), cpf)
                acc["ded_dependentes"][chave] = (
                    acc["ded_dependentes"].get(chave, 0.0) + valor
                )
                acc["usados"] |= rel

    def _ir_pensao(self, pagamento, slip, pensao, acc):
        linhas = self._linhas_desconto(slip, COD_IRRF_PENSAO)
        if not linhas:
            return
        total = sum(abs(ln.total) for ln in linhas)
        if len(pensao) == 1:
            cpf = self._cpf_parente(pensao, _("pensão alimentícia"), acc["erros"])
            if cpf:
                chave = (self._tp_rend(pagamento), cpf)
                acc["pen_alim"][chave] = acc["pen_alim"].get(chave, 0.0) + total
                acc["usados"] |= pensao
        elif not pensao:
            acc["erros"].append(
                _(
                    "'%(name)s' tem desconto de pensão alimentícia no holerite "
                    "%(slip)s, mas nenhum parente está marcado como "
                    "'Beneficiário da Pensão Alimentícia'."
                )
                % {
                    "name": self.employee_id.name,
                    "slip": slip.number or slip.display_name,
                }
            )

    def _ir_previdencia(self, pagamento, slip, contrato, acc):
        for linha in self._linhas_desconto(slip, COD_IRRF_PREV_COMPL):
            cod = linha.salary_rule_id.l10n_br_esocial_cod_inc_irrf
            if cod in COD_IRRF_PREV_PRIVADA:
                tp_prev = "1"
            elif cod in COD_IRRF_PREV_FAPI:
                tp_prev = "2"
            else:
                tp_prev = "3"
            cnpj = self._cnpj_contrato(
                contrato,
                "l10n_br_esocial_cnpj_prev_compl",
                _("CNPJ da Entidade de Previdência Complementar"),
                acc["erros"],
            )
            if cnpj:
                item = acc["previd"].setdefault(
                    (tp_prev, cnpj), {"mensal": 0.0, "decimo": 0.0}
                )
                decimo = self._tp_rend(pagamento) == "12"
                item["decimo" if decimo else "mensal"] += abs(linha.total)

    def _ir_plano_saude(self, slip, parentes, acc):
        linhas = self._linhas_desconto(slip, COD_IRRF_PLANO_SAUDE, NAT_RUBR_PLANO_SAUDE)
        if not linhas:
            return
        acc["tem_plano"] = True
        total = sum(abs(ln.total) for ln in linhas)
        deps = parentes.filtered("l10n_br_esocial_vlr_saude")
        soma_deps = sum(deps.mapped("l10n_br_esocial_vlr_saude"))
        if soma_deps > total + 0.005:
            acc["erros"].append(
                _(
                    "'%(name)s': os valores de plano de saúde dos dependentes "
                    "(%(deps).2f) passam do desconto do holerite %(slip)s "
                    "(%(total).2f)."
                )
                % {
                    "name": self.employee_id.name,
                    "deps": soma_deps,
                    "slip": slip.number or slip.display_name,
                    "total": total,
                }
            )
            return
        acc["plano_titular"] += total - soma_deps
        for rel in deps:
            cpf = self._cpf_parente(rel, _("plano de saúde"), acc["erros"])
            if cpf:
                acc["plano_deps"][cpf] = (
                    acc["plano_deps"].get(cpf, 0.0) + rel.l10n_br_esocial_vlr_saude
                )
                acc["usados"] |= rel

    def _ir_info_dep(self, usados):
        """Parentes que o IR cita e o S-2200 não cadastrou (sem tipo)."""
        info_dep = []
        for rel in usados.filtered(lambda r: not r.l10n_br_esocial_tp_dep_id):
            if not rel.date_of_birth:
                raise UserError(
                    _(
                        "Parente '%(dep)s' de '%(name)s' não está cadastrado no "
                        "eSocial como dependente: informe a Data de Nascimento "
                        "para declará-lo no S-1210 (infoDep)."
                    )
                    % {"dep": rel.name, "name": self.employee_id.name}
                )
            info_dep.append(
                {
                    "cpf_dep": self._so_digitos(rel.l10n_br_esocial_cpf),
                    "dt_nascto": str(rel.date_of_birth),
                    "nome": rel.name.strip(),
                }
            )
        return info_dep

    def _info_ir_complem(self):
        """Dados do infoIRComplem (``None`` se nenhum holerite o exige).

        Fontes: descontos dos holerites pagos neste evento, classificados pela
        incidência IRRF da rubrica; dependentes, beneficiário da pensão e
        valor do plano de saúde por parente, operadora e entidade no contrato.
        """
        self.ensure_one()
        contrato = self.pagamento_ids.mapped("payslip_id.contract_id")[:1]
        acc = {
            "erros": [],
            "ded_dependentes": OrderedDict(),
            "pen_alim": OrderedDict(),
            "previd": OrderedDict(),
            "tem_plano": False,
            "plano_titular": 0.0,
            "plano_deps": OrderedDict(),
            "usados": self.env["hr.employee.relative"],
        }
        parentes, pensao = self._parentes_ir(acc["erros"])
        dedutivel = parentes.filtered(
            lambda rel: rel.l10n_br_esocial_tp_dep_id and rel.l10n_br_esocial_dep_irrf
        )
        for pagamento in self.pagamento_ids.filtered("payslip_id"):
            slip = pagamento.payslip_id
            self._ir_dependentes(pagamento, slip, dedutivel, acc)
            self._ir_pensao(pagamento, slip, pensao, acc)
            self._ir_previdencia(pagamento, slip, contrato, acc)
            self._ir_plano_saude(slip, parentes, acc)
        cnpj_oper = None
        if acc["tem_plano"]:
            cnpj_oper = self._cnpj_contrato(
                contrato,
                "l10n_br_esocial_cnpj_oper_saude",
                _("CNPJ da Operadora do Plano de Saúde"),
                acc["erros"],
            )
        if acc["erros"]:
            raise UserError("\n".join(dict.fromkeys(acc["erros"])))
        if not (
            acc["ded_dependentes"]
            or acc["pen_alim"]
            or acc["previd"]
            or acc["tem_plano"]
        ):
            return None
        plano = None
        if acc["tem_plano"]:
            plano = {
                "cnpj_oper": cnpj_oper,
                "reg_ans": self._so_digitos(contrato.l10n_br_esocial_reg_ans),
                "titular": acc["plano_titular"],
                "dependentes": acc["plano_deps"],
            }
        return {
            "tp_cr": self._tp_cr(),
            "info_dep": self._ir_info_dep(acc["usados"]),
            "ded_dependentes": acc["ded_dependentes"],
            "pen_alim": acc["pen_alim"],
            "previd": acc["previd"],
            "plano": plano,
        }

    @staticmethod
    def _valor(numero):
        return "%.2f" % numero

    def _xml_info_ir_complem(self, ide_benef, ir):
        """Acrescenta o ``infoIRComplem`` ao ``ideBenef`` (ordem do XSD)."""
        filho = self._filho
        grupo = filho(ide_benef, "infoIRComplem")
        for dep in ir["info_dep"]:
            el = filho(grupo, "infoDep")
            filho(el, "cpfDep", dep["cpf_dep"])
            filho(el, "dtNascto", dep["dt_nascto"])
            filho(el, "nome", dep["nome"])
            # depIRRF só admite "S" (TS_depIRRF_IR): quem só recebe pensão ou
            # plano de saúde não é dependente para dedução e fica sem ele.
        if ir["ded_dependentes"] or ir["pen_alim"] or ir["previd"]:
            cr = filho(grupo, "infoIRCR")
            filho(cr, "tpCR", ir["tp_cr"])
            for (tp_rend, cpf), valor in ir["ded_dependentes"].items():
                el = filho(cr, "dedDepen")
                filho(el, "tpRend", tp_rend)
                filho(el, "cpfDep", cpf)
                filho(el, "vlrDedDep", self._valor(valor))
            for (tp_rend, cpf), valor in ir["pen_alim"].items():
                el = filho(cr, "penAlim")
                filho(el, "tpRend", tp_rend)
                filho(el, "cpfDep", cpf)
                filho(el, "vlrDedPenAlim", self._valor(valor))
            for (tp_prev, cnpj), valores in ir["previd"].items():
                el = filho(cr, "previdCompl")
                filho(el, "tpPrev", tp_prev)
                filho(el, "cnpjEntidPC", cnpj)
                if valores["mensal"]:
                    filho(el, "vlrDedPC", self._valor(valores["mensal"]))
                if valores["decimo"]:
                    filho(el, "vlrDedPC13", self._valor(valores["decimo"]))
        plano = ir["plano"]
        if plano:
            el = filho(grupo, "planSaude")
            filho(el, "cnpjOper", plano["cnpj_oper"])
            if plano["reg_ans"]:
                filho(el, "regANS", plano["reg_ans"])
            filho(el, "vlrSaudeTit", self._valor(plano["titular"]))
            for cpf, valor in plano["dependentes"].items():
                dep = filho(el, "infoDepSau")
                filho(dep, "cpfDep", cpf)
                filho(dep, "vlrSaudeDep", self._valor(valor))

    def _gerar_xml(self):
        self.ensure_one()
        self._check_esociallib()
        data = self._to_esociallib_dict()
        ir = self._info_ir_complem()
        _ensure_builders_loaded()
        evento = _BUILDERS["S-1210"](data, environment=self._get_tp_amb())
        if ir:
            ide_benef = evento._root.find(".//{*}ideBenef")
            self._xml_info_ir_complem(ide_benef, ir)
        xml = evento.to_xml()
        try:
            erros = validate_xsd(xml, "S-1210")
        except FileNotFoundError:
            _logger.error(
                "eSocial S-1210: schemas XSD ausentes na esociallib — XML gerado "
                "SEM validação XSD."
            )
            return xml
        # O XML ainda não está assinado: o XSD exige a Signature.
        erros = [e for e in erros if "Signature" not in e]
        if erros:
            raise UserError(
                _("O XML do S-1210 não passou na validação do leiaute:\n%s")
                % "\n".join(erros)
            )
        return xml


class ESocialS1210Pagamento(models.Model):
    _name = "l10n_br.esocial.s1210.pagamento"
    _description = "eSocial S-1210 - Pagamento (infoPgto)"
    _order = "dt_pgto, id"

    s1210_id = fields.Many2one(
        "l10n_br.esocial.s1210",
        string="S-1210",
        required=True,
        ondelete="cascade",
    )
    company_id = fields.Many2one(
        related="s1210_id.company_id",
        store=True,
        readonly=True,
    )
    currency_id = fields.Many2one(
        related="s1210_id.currency_id",
        readonly=True,
    )
    dt_pgto = fields.Date(
        string="Data Pagamento",
        required=True,
    )
    tp_pgto = fields.Selection(
        TP_PGTO,
        string="Tipo Pagamento",
        default="1",
        required=True,
    )
    per_ref = fields.Char(
        string="Período Referência",
        size=7,
        required=True,
        help="Competência da folha que originou o pagamento (AAAA-MM) ou o ano "
        "(AAAA) no caso do 13º salário.",
    )
    ide_dm_dev = fields.Char(
        string="Demonstrativo",
        size=30,
        required=True,
        help="Identificador do demonstrativo (ideDmDev) informado no S-1200 da "
        "competência de referência.",
    )
    vr_liq = fields.Monetary(
        string="Valor Líquido",
        required=True,
        currency_field="currency_id",
    )
    payslip_id = fields.Many2one(
        "hr.payslip",
        string="Holerite",
        ondelete="set null",
    )
    s1200_id = fields.Many2one(
        "l10n_br.esocial.s1200",
        string="S-1200 de Origem",
        ondelete="set null",
        help="Apuração que este pagamento liquida. É dela que sai o "
        "identificador do demonstrativo.",
    )

    @api.constrains("per_ref")
    def _check_per_ref(self):
        base = self.env["l10n_br.esocial.base.intermediario"]
        for rec in self:
            base._validar_competencia(rec.per_ref, _("Período Referência"), anual=True)

    @api.constrains("vr_liq")
    def _check_vr_liq(self):
        for rec in self:
            if rec.vr_liq <= 0:
                raise ValidationError(
                    _(
                        "Pagamento de %(data)s: o valor líquido pago deve ser "
                        "positivo (informado: %(valor)s). Holerite com líquido "
                        "zero ou negativo não gera pagamento no S-1210."
                    )
                    % {"data": rec.dt_pgto, "valor": rec.vr_liq}
                )

    def _to_esociallib_dict(self):
        self.ensure_one()
        return {
            "dt_pgto": fields.Date.to_string(self.dt_pgto),
            "tp_pgto": int(self.tp_pgto),
            "per_ref": self.per_ref,
            "ide_dm_dev": self.ide_dm_dev,
            "vr_liq": "%.2f" % self.vr_liq,
        }
