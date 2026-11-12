# Copyright 2026 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""Partes comuns do S-2300, S-2306 e S-2399 (trabalhador sem vínculo, TSVE)."""

import logging

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

# Categorias cujo S-2300 exige um grupo próprio (dirigente sindical, cedido,
# mandato eletivo) que este módulo ainda não gera: recusa em vez de enviar
# incompleto.
CATEGORIAS_GRUPO_NAO_SUPORTADO = {
    "304": "infoMandElet",
    "305": "infoTrabCedido",
    "401": "infoDirigenteSindical",
    "410": "infoTrabCedido",
}
CATEGORIAS_ESTAGIARIO = ("901", "906")
# natAtividade: obrigatório nestas categorias e proibido nas de CATEGORIAS_SEM_NAT.
CATEGORIAS_NAT_ATIVIDADE = ("201", "202", "401", "731", "734", "738")
CATEGORIAS_SEM_NAT = ("721", "722", "771", "901")
# O leiaute aceita dtInicio até 30 dias à frente e dtTerm até 10 dias à frente.
DIAS_INICIO_FUTURO = 30
DIAS_TERMINO_FUTURO = 10


class ESocialTSVMixin(models.AbstractModel):
    _name = "l10n_br.esocial.tsv.mixin"
    _inherit = "l10n_br.esocial.base.intermediario"
    _description = "eSocial - Trabalhador sem vínculo (S-2300, S-2306, S-2399)"

    employee_id = fields.Many2one(
        "hr.employee",
        string="Trabalhador",
        required=True,
        ondelete="cascade",
    )
    contract_id = fields.Many2one(
        "hr.contract",
        string="Contrato",
        required=True,
        ondelete="cascade",
    )

    # ------------------------------------------------------------------
    # Identificação e categoria
    # ------------------------------------------------------------------
    def _identificar(self, erros, evento):
        """CPF, matrícula, categoria e empregador, com as recusas reunidas."""
        employee = self.employee_id
        cpf = self._coletar(erros, self._get_cpf_limpo, employee)
        matricula = employee.l10n_br_esocial_matricula
        if not matricula:
            erros.append(
                _("Trabalhador '%(name)s' não possui Matrícula eSocial.")
                % {"name": employee.name}
            )
        categoria = employee.l10n_br_esocial_categoria_id
        if not categoria:
            erros.append(
                _("Trabalhador '%(name)s' não possui Categoria Trabalhador eSocial.")
                % {"name": employee.name}
            )
        else:
            self._coletar(
                erros, self._validar_categoria_evento, employee, categoria, evento
            )
            self._coletar(erros, self._validar_grupo_categoria, employee, categoria)
        ide = self._coletar(erros, self._get_ide_empregador)
        return cpf, matricula, categoria, ide

    def _validar_grupo_categoria(self, employee, categoria):
        grupo = CATEGORIAS_GRUPO_NAO_SUPORTADO.get(categoria.codigo)
        if grupo:
            self._erro_cadastro(
                _(
                    "Trabalhador '%(name)s': a categoria %(cat)s exige o grupo "
                    "%(grupo)s no evento, que este módulo ainda não gera."
                ),
                name=employee.name,
                cat=categoria.codigo,
                grupo=grupo,
            )

    def _erro_evento(self, evento, erros):
        raise UserError(
            _("%(evento)s de '%(name)s' não pode ser gerado; corrija o cadastro:")
            % {"evento": evento, "name": self.employee_id.name}
            + "\n- "
            + "\n- ".join(erros)
        )

    # ------------------------------------------------------------------
    # Informações complementares (S-2300 e S-2306)
    # ------------------------------------------------------------------
    def _get_cargo(self, employee, categoria):
        """nmCargo e CBOCargo do cargo do trabalhador (exceto categoria 410)."""
        job = employee.job_id
        if not job:
            self._erro_cadastro(
                _("Trabalhador '%(name)s': preencha o Cargo."), name=employee.name
            )
        cbo = job.cbo_id.code if "cbo_id" in job._fields else False
        if not cbo:
            self._erro_cadastro(
                _(
                    "Trabalhador '%(name)s': o cargo '%(cargo)s' não tem o CBO "
                    "(Classificação Brasileira de Ocupações)."
                ),
                name=employee.name,
                cargo=job.name,
            )
        return {"nm_cargo": job.name, "cod_cbo": self._so_digitos(cbo)}

    def _get_nat_atividade(self, contract, categoria):
        codigo = categoria.codigo
        valor = contract.l10n_br_esocial_nat_atividade
        if codigo in CATEGORIAS_NAT_ATIVIDADE and not valor:
            self._erro_cadastro(
                _(
                    "Contrato '%(name)s': a categoria %(cat)s exige a Natureza da "
                    "Atividade (urbana ou rural)."
                ),
                name=contract.display_name,
                cat=codigo,
            )
        if codigo in CATEGORIAS_SEM_NAT or not valor:
            return None
        return int(valor)

    def _get_estagiario(self, contract, categoria, dt_inicio):
        """Grupo infoEstagiario (categorias 901 e 906), só do cadastro."""
        nome = contract.display_name
        erros = []
        nat = contract.l10n_br_esocial_nat_estagio
        niv = contract.l10n_br_esocial_niv_estagio
        if not nat:
            erros.append(_("preencha a Natureza do Estágio"))
        elif categoria.codigo == "906" and nat != "N":
            erros.append(
                _("na categoria 906 a natureza do estágio é 'Não obrigatório'")
            )
        if categoria.codigo == "901" and not niv:
            erros.append(_("preencha o Nível do Estágio"))
        if categoria.codigo == "906" and niv == "9":
            erros.append(_("na categoria 906 o nível não pode ser 'Mãe social'"))
        fim = contract.date_end
        if not fim:
            erros.append(_("preencha a data de término prevista do contrato"))
        elif dt_inicio and str(fim) <= dt_inicio:
            erros.append(_("o término previsto deve ser posterior ao início"))
        inst = self._cnpj_parceiro(
            contract.l10n_br_esocial_inst_ensino_id,
            _("preencha a Instituição de Ensino (com CNPJ válido)"),
            erros,
        )
        agente = False
        if contract.l10n_br_esocial_age_integ_id:
            agente = self._cnpj_parceiro(
                contract.l10n_br_esocial_age_integ_id,
                _("o Agente de Integração precisa ter CNPJ válido"),
                erros,
            )
        supervisor = False
        sup = contract.l10n_br_esocial_supervisor_id
        if sup:
            supervisor = self._so_digitos(sup.cnpj_cpf)
            if len(supervisor) != 11 or (cnpj_cpf and not cnpj_cpf.validar(supervisor)):
                erros.append(_("o Supervisor do Estágio precisa ter CPF válido"))
        if erros:
            # ``_()`` fora de genexpr: dentro dele o Odoo não acha o idioma.
            linhas = []
            for erro in erros:
                linhas.append(
                    _("Contrato '%(name)s': %(erro)s.") % {"name": nome, "erro": erro}
                )
            raise UserError("\n".join(linhas))
        return {
            "nat_estagio": nat,
            "niv_estagio": niv or "",
            "area_atuacao": (contract.l10n_br_esocial_area_atuacao or "").strip(),
            "nr_apol": (contract.l10n_br_esocial_nr_apolice or "").strip(),
            "dt_prev_term": str(fim),
            "cnpj_inst_ensino": inst,
            "cnpj_age_integ": agente,
            "cpf_supervisor": supervisor,
        }

    def _cnpj_parceiro(self, partner, mensagem, erros):
        cnpj = self._so_digitos(partner.vat)
        if len(cnpj) != 14 or (cnpj_cpf and not cnpj_cpf.validar(cnpj)):
            erros.append(mensagem)
            return False
        return cnpj

    def _dados_complementares(self, erros, categoria, ide, dt_inicio):
        """Cargo, remuneração, local e estágio do contrato, no formato do builder."""
        employee = self.employee_id
        contract = self.contract_id
        data = {}
        if categoria and categoria.codigo != "410":
            data.update(
                self._coletar(erros, self._get_cargo, employee, categoria) or {}
            )
        if contract.wage:
            data["vr_sal_fx"] = "%.2f" % contract.wage
            data["und_sal_fixo"] = 5  # mensal
        if ide:
            local = self._coletar(erros, self._get_local_trabalho, employee, ide)
            if local:
                data["tp_insc_local"] = 1
                data["nr_insc_local"] = local
        if categoria:
            nat = self._coletar(erros, self._get_nat_atividade, contract, categoria)
            if nat is not None:
                data["nat_atividade"] = nat
            if categoria.codigo in CATEGORIAS_ESTAGIARIO:
                data["estagiario"] = self._coletar(
                    erros, self._get_estagiario, contract, categoria, dt_inicio
                )
        return data

    def _completar_estagiario(self, raiz, info, estagiario):
        """Acrescenta o infoEstagiario, que a esociallib 0.1.3 gera fora do leiaute.

        O builder grava ``instEstagiario`` (o leiaute chama ``instEnsino``, obrigatório),
        omite ``supervisorEstagio`` e só emite o grupo se houver natureza; por isso o
        grupo é montado aqui, na posição que o XSD exige (antes de ``localTrabGeral``).
        """
        if not estagiario:
            return
        ns = {"e": etree.QName(raiz[0]).namespace}
        pai = raiz.find(".//e:%s" % info, ns)
        compl = pai.find("e:infoComplementares", ns)
        if compl is None:
            compl = self._filho(pai, "infoComplementares")
        el = etree.Element("{%s}infoEstagiario" % ns["e"])
        self._filho(el, "natEstagio", estagiario["nat_estagio"])
        if estagiario["niv_estagio"]:
            self._filho(el, "nivEstagio", estagiario["niv_estagio"])
        if estagiario["area_atuacao"]:
            self._filho(el, "areaAtuacao", estagiario["area_atuacao"])
        if estagiario["nr_apol"]:
            self._filho(el, "nrApol", estagiario["nr_apol"])
        self._filho(el, "dtPrevTerm", estagiario["dt_prev_term"])
        inst = self._filho(el, "instEnsino")
        self._filho(inst, "cnpjInstEnsino", estagiario["cnpj_inst_ensino"])
        if estagiario["cnpj_age_integ"]:
            self._filho(
                self._filho(el, "ageIntegracao"),
                "cnpjAgntInteg",
                estagiario["cnpj_age_integ"],
            )
        if estagiario["cpf_supervisor"]:
            self._filho(
                self._filho(el, "supervisorEstagio"),
                "cpfSupervisor",
                estagiario["cpf_supervisor"],
            )
        local = compl.find("e:localTrabGeral", ns)
        if local is not None:
            local.addprevious(el)
        else:
            compl.append(el)

    # ------------------------------------------------------------------
    # XML
    # ------------------------------------------------------------------
    def _montar_xml(self, completar=None):
        """Gera o XML do evento pela esociallib, completa e valida no XSD."""
        self.ensure_one()
        self._check_esociallib()
        evento_tipo = self._get_event_type()
        data = self._to_esociallib_dict()
        _ensure_builders_loaded()
        evento = _BUILDERS[evento_tipo](data, environment=self._get_tp_amb())
        if completar:
            completar(evento._root, data)
        xml = evento.to_xml()
        try:
            erros = validate_xsd(xml, evento_tipo)
        except FileNotFoundError:
            _logger.error(
                "eSocial %s: schemas XSD ausentes na esociallib — XML gerado "
                "SEM validação XSD.",
                evento_tipo,
            )
            return xml
        # O XML ainda não está assinado: o XSD exige a Signature.
        erros = [e for e in erros if "Signature" not in e]
        if erros:
            raise UserError(
                _("O XML do %(evento)s não passou na validação do leiaute:\n%(erros)s")
                % {"evento": evento_tipo, "erros": "\n".join(erros)}
            )
        return xml
