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

# Raça/cor aceita no S-2200 (TS_racaCorTrab, S-1.3): o 6 (não informado) existe
# na tabela, mas é proibido neste evento.
RACA_COR = {"1", "2", "3", "4", "5"}
# A partir desta data de admissão o leiaute S-1.3 limita as horas do tempo
# parcial e exige tmpParc = 0 na jornada 12 x 36.
DT_REGRA_TEMPO_PARCIAL = "2026-11-23"
LIMITE_HORAS_TEMPO_PARCIAL = {1: 25.0, 2: 30.0, 3: 26.0}
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

    avisos = fields.Text(
        string="Avisos da geração",
        readonly=True,
        copy=False,
        help="Divergências que não impedem o evento, como dependentes de IRRF "
        "e de salário-família da folha diferentes dos declarados.",
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
        if codigo == "6":
            self._erro_cadastro(
                _(
                    "Empregado '%(name)s': a Raça/Cor 'Não informado' (6) não pode "
                    "ser enviada no S-2200; preencha a Raça/Cor do cadastro."
                ),
                name=employee.name,
            )
        if codigo not in RACA_COR:
            self._erro_cadastro(
                _(
                    "Empregado '%(name)s': preencha Raça/Cor no cadastro (código "
                    "de 1 a 5 da tabela do eSocial)."
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

    def _get_jornada(self, contract, cod_categ, dt_adm):
        """qtdHrsSem, tpJornada, tmpParc, horNoturno e dscJorn do contrato."""
        calendar = contract.resource_calendar_id
        linhas = calendar.attendance_ids.filtered(
            lambda a: not a.display_type and a.day_period != "lunch"
        )
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
        tp_jornada = int(contract.l10n_br_esocial_tp_jornada)
        tmp_parc = int(contract.l10n_br_esocial_tmp_parc or 0)
        self._validar_tempo_parcial(
            contract, tmp_parc, tp_jornada, horas, cod_categ, dt_adm
        )
        noturno = any(
            a.hour_to > INICIO_NOTURNO or a.hour_from < FIM_NOTURNO for a in linhas
        )
        return {
            "qtd_hrs_sem": "%.2f" % horas,
            "tp_jornada": tp_jornada,
            "tmp_parc": tmp_parc,
            "hor_noturno": "S" if noturno else "N",
            "dsc_jorn": self._descrever_jornada(linhas, calendar.two_weeks_calendar),
        }

    def _validar_tempo_parcial(
        self, contract, tmp_parc, tp_jornada, horas, cod_categ, dt_adm
    ):
        """Regras do leiaute S-1.3 para tmpParc (categoria, jornada e horas)."""
        nome = contract.display_name
        if tmp_parc == 1 and cod_categ != "104":
            self._erro_cadastro(
                _(
                    "Contrato '%(name)s': Tempo Parcial 1 (até 25h) só vale para a "
                    "categoria 104 (doméstico)."
                ),
                name=nome,
            )
        if tmp_parc in (2, 3) and cod_categ == "104":
            self._erro_cadastro(
                _(
                    "Contrato '%(name)s': Tempo Parcial %(tmp)s não vale para a "
                    "categoria 104 (doméstico)."
                ),
                name=nome,
                tmp=tmp_parc,
            )
        if not dt_adm or dt_adm < DT_REGRA_TEMPO_PARCIAL:
            return
        if tp_jornada == 2 and tmp_parc != 0:
            self._erro_cadastro(
                _(
                    "Contrato '%(name)s': na jornada 12 x 36 com admissão a partir "
                    "de 23/11/2026 o Tempo Parcial deve ser 0."
                ),
                name=nome,
            )
        limite = LIMITE_HORAS_TEMPO_PARCIAL.get(tmp_parc)
        if limite and horas > limite:
            self._erro_cadastro(
                _(
                    "Contrato '%(name)s': a jornada de %(horas).2f h semanais passa "
                    "do limite de %(limite).0f h do Tempo Parcial %(tmp)s."
                ),
                name=nome,
                horas=horas,
                limite=limite,
                tmp=tmp_parc,
            )

    @staticmethod
    def _formatar_hora(valor):
        horas, minutos = divmod(int(round(valor * 60)), 60)
        return "%02d:%02d" % (horas, minutos)

    def _descrever_semana(self, linhas):
        por_dia = OrderedDict()
        for linha in linhas.sorted(lambda a: (int(a.dayofweek), a.hour_from)):
            por_dia.setdefault(int(linha.dayofweek), []).append(
                "%s-%s"
                % (
                    self._formatar_hora(linha.hour_from),
                    self._formatar_hora(linha.hour_to),
                )
            )
        return "; ".join(
            "%s: %s" % (DIAS_SEMANA[dia], ", ".join(faixas))
            for dia, faixas in por_dia.items()
        )

    def _descrever_jornada(self, linhas, duas_semanas=False):
        """Dias da semana com os horários de entrada e saída (dscJorn).

        No calendário de duas semanas descreve cada semana à parte.
        """
        if not duas_semanas:
            return self._descrever_semana(linhas)[:999]
        partes = []
        for n, tipo in enumerate(("0", "1"), start=1):
            semana = linhas.filtered(lambda a, t=tipo: a.week_type == t)
            if semana:
                partes.append("Semana %d - %s" % (n, self._descrever_semana(semana)))
        return " | ".join(partes)[:999]

    def _dependente(self, rel, employee, hoje):
        nome = (rel.name or "").strip()
        erros = []
        tipo = rel.l10n_br_esocial_tp_dep_id
        if not rel.date_of_birth:
            erros.append(_("preencha a Data de Nascimento"))
        elif rel.date_of_birth > hoje:
            erros.append(_("a Data de Nascimento está no futuro"))
        if tipo.dt_fim and tipo.dt_fim < hoje:
            erros.append(
                _("o tipo '%(tipo)s' foi encerrado na Tabela 07 em %(dt)s")
                % {"tipo": tipo.display_name, "dt": tipo.dt_fim}
            )
        cpf = self._so_digitos(rel.l10n_br_esocial_cpf)
        if rel.l10n_br_esocial_dep_irrf and not cpf:
            erros.append(_("o CPF é obrigatório quando é dependente para IRRF"))
        if cpf and (len(cpf) != 11 or (cnpj_cpf and not cnpj_cpf.validar(cpf))):
            erros.append(_("CPF inválido"))
        descr = (rel.l10n_br_esocial_descr_dep or "").strip()
        if tipo.codigo == "99" and not descr:
            erros.append(_("a descrição da dependência é obrigatória para o tipo 99"))
        if erros:
            raise UserError(
                "\n".join(
                    _("Dependente '%(dep)s' de '%(name)s': %(erro)s.")
                    % {"dep": nome, "name": employee.name, "erro": erro}
                    for erro in erros
                )
            )
        return {
            "tp_dep": tipo.codigo,
            "nm_dep": nome,
            "dt_nascto": str(rel.date_of_birth),
            "cpf_dep": cpf,
            "dep_irrf": "S" if rel.l10n_br_esocial_dep_irrf else "N",
            "dep_sf": "S" if rel.l10n_br_esocial_dep_sf else "N",
            "inc_trab": "S" if rel.l10n_br_esocial_inc_trab else "N",
            "descr_dep": descr if tipo.codigo == "99" else "",
        }

    def _get_dependentes(self, employee):
        """Parentes com tipo de dependente eSocial, no formato do grupo.

        Parente com IRRF, salário-família ou incapacidade marcados e sem tipo
        é recusado (não pode sumir do evento sem aviso).
        """
        hoje = fields.Date.context_today(self)
        erros = []
        dependentes = []
        cpfs = {}
        for rel in employee.relative_ids:
            if not rel.l10n_br_esocial_tp_dep_id:
                if (
                    rel.l10n_br_esocial_dep_irrf
                    or rel.l10n_br_esocial_dep_sf
                    or rel.l10n_br_esocial_inc_trab
                ):
                    erros.append(
                        _(
                            "Dependente '%(dep)s' de '%(name)s': marcado para "
                            "IRRF/salário-família/incapacidade, mas sem o Tipo de "
                            "Dependente eSocial."
                        )
                        % {"dep": rel.name, "name": employee.name}
                    )
                continue
            try:
                dep = self._dependente(rel, employee, hoje)
            except UserError as erro:
                erros.append(erro.args[0])
                continue
            if dep["cpf_dep"] and dep["cpf_dep"] in cpfs:
                erros.append(
                    _(
                        "Dependente '%(dep)s' de '%(name)s': CPF repetido em "
                        "outro dependente."
                    )
                    % {"dep": dep["nm_dep"], "name": employee.name}
                )
                continue
            cpfs[dep["cpf_dep"]] = True
            dependentes.append(dep)
        if erros:
            raise UserError("\n".join(erros))
        return dependentes

    def _avisos_dependentes(self, employee, dependentes):
        """Divergência entre a folha (IRRF/salário-família) e o declarado."""
        avisos = []
        pares = (
            (
                "l10n_br_irrf_dependentes",
                "dep_irrf",
                _("Dependentes IRRF da folha"),
            ),
            (
                "l10n_br_num_filhos_sf",
                "dep_sf",
                _("Filhos para Salário-Família da folha"),
            ),
        )
        for campo, chave, rotulo in pares:
            folha = employee[campo] if campo in employee._fields else None
            declarados = sum(1 for d in dependentes if d[chave] == "S")
            if folha is not None and folha != declarados:
                avisos.append(
                    _("%(rotulo)s: %(folha)s, mas o S-2200 declara %(dep)s.")
                    % {"rotulo": rotulo, "folha": folha, "dep": declarados}
                )
        return avisos

    @staticmethod
    def _coletar(erros, funcao, *args):
        """Chama ``funcao``; se recusar, guarda a mensagem e devolve ``None``."""
        try:
            return funcao(*args)
        except UserError as erro:
            erros.append(erro.args[0])
            return None

    def _to_esociallib_dict(self):
        """Dict do S-2200, ou ``UserError`` com TODOS os dados que faltam."""
        self.ensure_one()
        employee = self.employee_id
        contract = self.contract_id
        erros = []

        cpf_limpo = self._coletar(erros, self._get_cpf_limpo, employee)
        matricula = employee.l10n_br_esocial_matricula
        if not matricula:
            erros.append(
                _("Empregado '%(name)s' não possui Matrícula eSocial.")
                % {"name": employee.name}
            )
        categoria = employee.l10n_br_esocial_categoria_id
        if not categoria:
            erros.append(
                _("Empregado '%(name)s' não possui Categoria Trabalhador eSocial.")
                % {"name": employee.name}
            )

        ide = self._coletar(erros, self._get_ide_empregador)
        proc = self._get_proc_info()
        dt_adm = str(contract.date_start) if contract.date_start else ""
        cod_categ = categoria.codigo if categoria else ""

        sexo = self._coletar(erros, self._get_sexo, employee)
        raca_cor = self._coletar(erros, self._get_raca_cor, employee)
        grau_instr = self._coletar(erros, self._get_grau_instr, employee)
        dt_nascto = self._coletar(erros, self._get_dt_nascto, employee)
        cnpj_sind = self._coletar(erros, self._get_cnpj_sindicato, contract)
        local = (
            self._coletar(erros, self._get_local_trabalho, employee, ide)
            if ide
            else None
        )
        jornada = self._coletar(erros, self._get_jornada, contract, cod_categ, dt_adm)
        dependentes = self._coletar(erros, self._get_dependentes, employee)

        if erros:
            raise UserError(
                _("S-2200 de '%(name)s' não pode ser gerado; corrija o cadastro:")
                % {"name": employee.name}
                + "\n- "
                + "\n- ".join(erros)
            )

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
            "sexo": sexo,
            "raca_cor": raca_cor,
            "grau_instr": grau_instr,
            "dt_nascto": dt_nascto,
            "matricula": matricula,
            "tp_reg_trab": 1,  # CLT
            "tp_reg_prev": 1,  # RGPS
            "cod_categ": cod_categ,
        }

        est_civ = marital_map.get(employee.marital)
        if est_civ:
            data["est_civ"] = est_civ

        # CLT fields
        if dt_adm:
            data["dt_adm"] = dt_adm
        data["nat_atividade"] = 1  # Normal
        data["cnpj_sind_categ_prof"] = cnpj_sind

        # Local de trabalho (estabelecimento do empregador) e jornada
        data["tp_insc_local"] = 1
        data["nr_insc_local"] = local
        data.update(jornada)
        data["dependentes"] = dependentes
        self._registrar_avisos(self._avisos_dependentes(employee, dependentes))

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

    def _registrar_avisos(self, avisos):
        """Guarda (campo ``avisos`` e log) o que não impede o evento."""
        self.avisos = "\n".join(avisos) if avisos else False
        if avisos:
            _logger.warning(
                "eSocial S-2200 %s (%s): %s",
                self.id,
                self.employee_id.name,
                self.avisos,
            )

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
