# Copyright 2026 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""Dados do trabalhador comuns ao S-2200 (vínculo) e ao S-2300 (sem vínculo)."""

import logging

from lxml import etree

from odoo import _, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

try:
    from erpbrasil.base.fiscal import cnpj_cpf
except ImportError:  # pragma: no cover
    cnpj_cpf = None

# Raça/cor aceita no S-2200 e no S-2300 (TS_racaCorTrab, S-1.3): o 6 (não
# informado) existe na tabela, mas é proibido nestes eventos.
RACA_COR = {"1", "2", "3", "4", "5"}


class ESocialTrabalhadorMixin(models.AbstractModel):
    _name = "l10n_br.esocial.trabalhador.mixin"
    _inherit = "l10n_br.esocial.base.intermediario"
    _description = "eSocial - Dados do trabalhador (S-2200 e S-2300)"

    avisos = fields.Text(
        string="Avisos da geração",
        readonly=True,
        copy=False,
        help="Divergências que não impedem o evento, como dependentes de IRRF "
        "e de salário-família da folha diferentes dos declarados.",
    )

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
            # ``_()`` fora de genexpr: dentro dele o Odoo não acha o idioma.
            linhas = []
            for erro in erros:
                linhas.append(
                    _("Dependente '%(dep)s' de '%(name)s': %(erro)s.")
                    % {"dep": nome, "name": employee.name, "erro": erro}
                )
            raise UserError("\n".join(linhas))
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

    def _xml_dependentes(self, trabalhador, dependentes):
        """Acrescenta ao ``trabalhador`` os dependentes que a esociallib não gera."""
        ns = etree.QName(trabalhador).namespace
        contato = trabalhador.find("{%s}contato" % ns)
        for dep in dependentes:
            el = etree.Element("{%s}dependente" % ns)
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
