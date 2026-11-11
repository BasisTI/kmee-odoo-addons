# Copyright 2024 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import logging
from collections import OrderedDict

from lxml import etree

from odoo import _, fields, models
from odoo.exceptions import UserError

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

# Tabela de raça/cor (racaCor) do leiaute S-1.3, TS_racaCor.
RACA_COR = {"1", "2", "3", "4", "5", "6"}
DIAS_SEMANA = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"]
# Horário noturno do trabalhador urbano (CLT, art. 73 §2º): 22h às 5h.
INICIO_NOTURNO = 22.0
FIM_NOTURNO = 5.0


class ESocialS2200(models.Model):
    _name = "l10n_br.esocial.s2200"
    _inherit = "l10n_br.esocial.base.intermediario"
    _description = "eSocial S-2200 - Cadastramento Inicial / Admissão"

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

    def _get_event_type(self):
        return "S-2200"

    def _get_cpf_limpo(self, employee):
        cpf = employee.cnpj_cpf
        if not cpf:
            raise UserError(
                _("Empregado '%(name)s' não possui CPF configurado.")
                % {"name": employee.name}
            )
        return "".join(c for c in cpf if c.isdigit())

    def _erro_cadastro(self, mensagem, **valores):
        raise UserError(mensagem % valores)

    def _get_sexo(self, employee):
        sexo = {"male": "M", "female": "F"}.get(employee.gender)
        if not sexo:
            self._erro_cadastro(
                _(
                    "Empregado '%(name)s': o eSocial só aceita sexo Masculino ou "
                    "Feminino; preencha o campo Gênero do cadastro."
                ),
                name=employee.name,
            )
        return sexo

    def _get_raca_cor(self, employee):
        codigo = (employee.ethnicity.code or "").strip()
        if codigo not in RACA_COR:
            self._erro_cadastro(
                _(
                    "Empregado '%(name)s': preencha Raça/Cor no cadastro (código "
                    "de 1 a 6 da tabela do eSocial)."
                ),
                name=employee.name,
            )
        return int(codigo)

    def _get_grau_instr(self, employee):
        if not employee.l10n_br_esocial_grau_instr:
            self._erro_cadastro(
                _(
                    "Empregado '%(name)s': preencha o Grau de Instrução eSocial "
                    "no cadastro."
                ),
                name=employee.name,
            )
        return employee.l10n_br_esocial_grau_instr

    def _get_dt_nascto(self, employee):
        if not employee.birthday:
            self._erro_cadastro(
                _("Empregado '%(name)s': preencha a Data de Nascimento."),
                name=employee.name,
            )
        return str(employee.birthday)

    def _get_cnpj_sindicato(self, contract):
        cnpj = self._so_digitos(contract.union_cnpj)
        if len(cnpj) != 14 or (cnpj_cpf and not cnpj_cpf.validar(cnpj)):
            self._erro_cadastro(
                _(
                    "Contrato '%(name)s': informe o Sindicato (com CNPJ válido) "
                    "da categoria do empregado."
                ),
                name=contract.display_name,
            )
        return cnpj

    def _get_local_trabalho(self, employee, ide):
        """Estabelecimento do empregador onde o empregado trabalha (CNPJ)."""
        partner = employee.address_id
        cnpj = self._so_digitos(partner.vat)
        if len(cnpj) != 14:
            self._erro_cadastro(
                _(
                    "Empregado '%(name)s': o Endereço de Trabalho precisa ser o "
                    "estabelecimento do empregador, com CNPJ de 14 dígitos."
                ),
                name=employee.name,
            )
        if ide["tp_insc"] == 1 and cnpj[:8] != ide["nr_insc"]:
            self._erro_cadastro(
                _(
                    "Empregado '%(name)s': o CNPJ do Endereço de Trabalho "
                    "(%(cnpj)s) não pertence ao empregador (raiz %(raiz)s)."
                ),
                name=employee.name,
                cnpj=cnpj,
                raiz=ide["nr_insc"],
            )
        return cnpj

    def _get_jornada(self, contract):
        """qtdHrsSem, tpJornada, tmpParc, horNoturno e dscJorn do contrato."""
        calendar = contract.resource_calendar_id
        linhas = calendar.attendance_ids.filtered(lambda a: not a.display_type)
        horas = contract._l10n_br_horas_semanais()
        if not calendar or not linhas or horas <= 0:
            self._erro_cadastro(
                _(
                    "Contrato '%(name)s': informe a Jornada de Trabalho "
                    "(calendário com os horários de presença)."
                ),
                name=contract.display_name,
            )
        if not contract.l10n_br_esocial_tp_jornada:
            self._erro_cadastro(
                _("Contrato '%(name)s': preencha o Tipo de Jornada eSocial."),
                name=contract.display_name,
            )
        noturno = any(
            a.hour_to > INICIO_NOTURNO or a.hour_from < FIM_NOTURNO for a in linhas
        )
        return {
            "qtd_hrs_sem": "%.2f" % horas,
            "tp_jornada": int(contract.l10n_br_esocial_tp_jornada),
            "tmp_parc": int(contract.l10n_br_esocial_tmp_parc or 0),
            "hor_noturno": "S" if noturno else "N",
            "dsc_jorn": self._descrever_jornada(linhas),
        }

    @staticmethod
    def _formatar_hora(valor):
        horas, minutos = divmod(int(round(valor * 60)), 60)
        return "%02d:%02d" % (horas, minutos)

    def _descrever_jornada(self, linhas):
        """Dias da semana com os horários de entrada e saída (dscJorn)."""
        por_dia = OrderedDict()
        for linha in linhas.sorted(lambda a: (int(a.dayofweek), a.hour_from)):
            por_dia.setdefault(int(linha.dayofweek), []).append(
                "%s-%s"
                % (
                    self._formatar_hora(linha.hour_from),
                    self._formatar_hora(linha.hour_to),
                )
            )
        partes = [
            "%s: %s" % (DIAS_SEMANA[dia], ", ".join(faixas))
            for dia, faixas in por_dia.items()
        ]
        return "; ".join(partes)[:999]

    def _get_dependentes(self, employee):
        """Parentes com tipo de dependente eSocial, no formato do grupo."""
        dependentes = []
        cpfs = set()
        for rel in employee.relative_ids.filtered("l10n_br_esocial_tp_dep_id"):
            nome = rel.name
            if not rel.date_of_birth:
                self._erro_cadastro(
                    _(
                        "Dependente '%(dep)s' de '%(name)s': preencha a Data de "
                        "Nascimento."
                    ),
                    dep=nome,
                    name=employee.name,
                )
            cpf = self._so_digitos(rel.l10n_br_esocial_cpf)
            if rel.l10n_br_esocial_dep_irrf and not cpf:
                self._erro_cadastro(
                    _(
                        "Dependente '%(dep)s' de '%(name)s': o CPF é obrigatório "
                        "quando é dependente para IRRF."
                    ),
                    dep=nome,
                    name=employee.name,
                )
            if cpf and (len(cpf) != 11 or (cnpj_cpf and not cnpj_cpf.validar(cpf))):
                self._erro_cadastro(
                    _("Dependente '%(dep)s' de '%(name)s': CPF inválido."),
                    dep=nome,
                    name=employee.name,
                )
            if cpf and cpf in cpfs:
                self._erro_cadastro(
                    _(
                        "Dependente '%(dep)s' de '%(name)s': CPF repetido em "
                        "outro dependente."
                    ),
                    dep=nome,
                    name=employee.name,
                )
            cpfs.add(cpf)
            tipo = rel.l10n_br_esocial_tp_dep_id.codigo
            descr = (rel.l10n_br_esocial_descr_dep or "").strip()
            if tipo == "99" and not descr:
                self._erro_cadastro(
                    _(
                        "Dependente '%(dep)s' de '%(name)s': a descrição da "
                        "dependência é obrigatória para o tipo 99."
                    ),
                    dep=nome,
                    name=employee.name,
                )
            dependentes.append(
                {
                    "tp_dep": tipo,
                    "nm_dep": nome.strip(),
                    "dt_nascto": str(rel.date_of_birth),
                    "cpf_dep": cpf,
                    "dep_irrf": "S" if rel.l10n_br_esocial_dep_irrf else "N",
                    "dep_sf": "S" if rel.l10n_br_esocial_dep_sf else "N",
                    "inc_trab": "S" if rel.l10n_br_esocial_inc_trab else "N",
                    "descr_dep": descr if tipo == "99" else "",
                }
            )
        return dependentes

    def _to_esociallib_dict(self):
        self.ensure_one()
        employee = self.employee_id
        contract = self.contract_id

        cpf_limpo = self._get_cpf_limpo(employee)
        matricula = employee.l10n_br_esocial_matricula
        if not matricula:
            raise UserError(
                _("Empregado '%(name)s' não possui Matrícula eSocial.")
                % {"name": employee.name}
            )

        categoria = employee.l10n_br_esocial_categoria_id
        if not categoria:
            raise UserError(
                _("Empregado '%(name)s' não possui Categoria Trabalhador eSocial.")
                % {"name": employee.name}
            )

        ide = self._get_ide_empregador()
        proc = self._get_proc_info()

        # Marital mapping to eSocial estCiv
        marital_map = {
            "single": 1,
            "married": 2,
            "divorced": 3,
            "widower": 5,
        }

        data = {
            "tp_insc": ide["tp_insc"],
            "nr_insc": ide["nr_insc"],
            "proc_emi": proc["proc_emi"],
            "ver_proc": proc["ver_proc"],
            "cpf_trab": cpf_limpo,
            "nm_trab": employee.name,
            "sexo": self._get_sexo(employee),
            "raca_cor": self._get_raca_cor(employee),
            "grau_instr": self._get_grau_instr(employee),
            "dt_nascto": self._get_dt_nascto(employee),
            "matricula": matricula,
            "tp_reg_trab": 1,  # CLT
            "tp_reg_prev": 1,  # RGPS
            "cod_categ": categoria.codigo,
        }

        est_civ = marital_map.get(employee.marital)
        if est_civ:
            data["est_civ"] = est_civ

        # CLT fields
        if contract.date_start:
            data["dt_adm"] = str(contract.date_start)
        data["nat_atividade"] = 1  # Normal
        data["cnpj_sind_categ_prof"] = self._get_cnpj_sindicato(contract)

        # Local de trabalho (estabelecimento do empregador) e jornada
        data["tp_insc_local"] = 1
        data["nr_insc_local"] = self._get_local_trabalho(employee, ide)
        data.update(self._get_jornada(contract))
        data["dependentes"] = self._get_dependentes(employee)

        # Salary
        if contract.wage:
            data["vr_sal_fx"] = str(contract.wage)
            data["und_sal_fixo"] = 5  # Mensal

        # CBO
        cbo = getattr(employee, "job_id", None)
        if cbo and hasattr(cbo, "l10n_br_cbo_id"):
            cbo_code = getattr(cbo.l10n_br_cbo_id, "code", None)
            if cbo_code:
                data["cod_cbo"] = cbo_code

        # Position name
        if employee.job_id:
            data["nm_cargo"] = employee.job_id.name

        return data

    # ------------------------------------------------------------------
    # XML: a esociallib 0.1.3 não emite dependentes nem os campos
    # tmpParc/horNoturno/dscJorn do horário contratual (obrigatórios no XSD).
    # ------------------------------------------------------------------
    @staticmethod
    def _filho(pai, tag, texto=None):
        ns = etree.QName(pai).namespace
        el = etree.SubElement(pai, "{%s}%s" % (ns, tag))
        if texto is not None:
            el.text = str(texto)
        return el

    def _completar_xml(self, raiz, data):
        """Acrescenta ao XML da esociallib o que ela não gera."""
        ns = {"e": etree.QName(raiz[0]).namespace}
        trabalhador = raiz.find(".//e:trabalhador", ns)
        contato = trabalhador.find("e:contato", ns)
        for dep in data["dependentes"]:
            el = etree.Element("{%s}dependente" % ns["e"])
            self._filho(el, "tpDep", dep["tp_dep"])
            self._filho(el, "nmDep", dep["nm_dep"])
            self._filho(el, "dtNascto", dep["dt_nascto"])
            if dep["cpf_dep"]:
                self._filho(el, "cpfDep", dep["cpf_dep"])
            self._filho(el, "depIRRF", dep["dep_irrf"])
            self._filho(el, "depSF", dep["dep_sf"])
            self._filho(el, "incTrab", dep["inc_trab"])
            if dep["descr_dep"]:
                self._filho(el, "descrDep", dep["descr_dep"])
            if contato is not None:
                contato.addprevious(el)
            else:
                trabalhador.append(el)
        hor = raiz.find(".//e:horContratual", ns)
        self._filho(hor, "tmpParc", data["tmp_parc"])
        self._filho(hor, "horNoturno", data["hor_noturno"])
        self._filho(hor, "dscJorn", data["dsc_jorn"])

    def _gerar_xml(self):
        self.ensure_one()
        self._check_esociallib()
        data = self._to_esociallib_dict()
        _ensure_builders_loaded()
        evento = _BUILDERS["S-2200"](data, environment=self._get_tp_amb())
        self._completar_xml(evento._root, data)
        xml = evento.to_xml()
        try:
            erros = validate_xsd(xml, "S-2200")
        except FileNotFoundError:
            _logger.error(
                "eSocial S-2200: schemas XSD ausentes na esociallib — XML gerado "
                "SEM validação XSD."
            )
            return xml
        # O XML ainda não está assinado: o XSD exige a Signature.
        erros = [e for e in erros if "Signature" not in e]
        if erros:
            raise UserError(
                _("O XML do S-2200 não passou na validação do leiaute:\n%s")
                % "\n".join(erros)
            )
        return xml
