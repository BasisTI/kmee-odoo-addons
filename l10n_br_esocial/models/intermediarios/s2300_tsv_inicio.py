# Copyright 2026 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from datetime import timedelta

from lxml import etree

from odoo import _, fields, models

from .tsv_mixin import DIAS_INICIO_FUTURO

ESTADO_CIVIL = {"single": 1, "married": 2, "divorced": 3, "widower": 5}


class ESocialS2300(models.Model):
    _name = "l10n_br.esocial.s2300"
    _inherit = [
        "l10n_br.esocial.trabalhador.mixin",
        "l10n_br.esocial.tsv.mixin",
    ]
    _description = "eSocial S-2300 - Trabalhador sem vínculo - Início"

    cad_ini = fields.Selection(
        [
            ("N", "Não - início de TSVE"),
            ("S", "Sim - cadastramento inicial"),
        ],
        string="Cadastramento inicial",
        required=True,
        default="N",
        help="'Sim' quando o ingresso do trabalhador é anterior ao início da "
        "obrigatoriedade dos eventos não periódicos do empregador.",
    )

    def _get_event_type(self):
        return "S-2300"

    def _get_pais(self, country, rotulo, employee):
        """Código da Tabela 06 (país) a partir do código do Bacen do país.

        O eSocial usa os 3 primeiros dígitos do código do Bacen de 4 dígitos
        (Brasil: Bacen 1058, eSocial 105); só vale se existir na Tabela 06.
        """
        bacen = self._so_digitos(
            country.bc_code if "bc_code" in country._fields else ""
        )
        codigo = bacen.zfill(4)[:3] if bacen else ""
        pais = self.env["l10n_br.esocial.pais"].search(
            [("codigo", "=", codigo), ("dt_fim", "=", False)], limit=1
        )
        if not pais:
            self._erro_cadastro(
                _(
                    "Trabalhador '%(name)s': preencha o %(rotulo)s com um país que "
                    "tenha o código do Bacen e conste da Tabela 06 do eSocial."
                ),
                name=employee.name,
                rotulo=rotulo,
            )
        return pais.codigo

    def _get_dt_inicio(self, contract, employee):
        if not contract.date_start:
            self._erro_cadastro(
                _("Contrato '%(name)s': preencha a data de início."),
                name=contract.display_name,
            )
        inicio = contract.date_start
        limite = fields.Date.context_today(self) + timedelta(days=DIAS_INICIO_FUTURO)
        if inicio > limite:
            self._erro_cadastro(
                _(
                    "Contrato '%(name)s': o início (%(inicio)s) passa de %(dias)s "
                    "dias à frente da data atual."
                ),
                name=contract.display_name,
                inicio=inicio,
                dias=DIAS_INICIO_FUTURO,
            )
        if employee.birthday and inicio <= employee.birthday:
            self._erro_cadastro(
                _(
                    "Contrato '%(name)s': o início deve ser posterior ao "
                    "nascimento do trabalhador."
                ),
                name=contract.display_name,
            )
        return str(inicio)

    def _to_esociallib_dict(self):
        """Dict do S-2300, ou ``UserError`` com TODOS os dados que faltam."""
        self.ensure_one()
        employee = self.employee_id
        contract = self.contract_id
        erros = []
        cpf, matricula, categoria, ide = self._identificar(erros, "S-2300")
        proc = self._get_proc_info()
        dt_inicio = self._coletar(erros, self._get_dt_inicio, contract, employee)
        sexo = self._coletar(erros, self._get_sexo, employee)
        raca_cor = self._coletar(erros, self._get_raca_cor, employee)
        grau_instr = self._coletar(erros, self._get_grau_instr, employee)
        dt_nascto = self._coletar(erros, self._get_dt_nascto, employee)
        pais_nascto = self._coletar(
            erros,
            self._get_pais,
            employee.country_of_birth,
            _("País de Nascimento"),
            employee,
        )
        pais_nac = self._coletar(
            erros,
            self._get_pais,
            employee.country_id,
            _("País de Nacionalidade"),
            employee,
        )
        dependentes = self._coletar(erros, self._get_dependentes, employee)
        compl = self._dados_complementares(erros, categoria, ide, dt_inicio)
        if erros:
            self._erro_evento("S-2300", erros)

        data = {
            "tp_insc": ide["tp_insc"],
            "nr_insc": ide["nr_insc"],
            "proc_emi": proc["proc_emi"],
            "ver_proc": proc["ver_proc"],
            "cpf_trab": cpf,
            "nm_trab": employee.name,
            "sexo": sexo,
            "raca_cor": raca_cor,
            "grau_instr": grau_instr,
            "dt_nascto": dt_nascto,
            "pais_nascto": pais_nascto,
            "pais_nac": pais_nac,
            "cad_ini": self.cad_ini,
            "matricula": matricula,
            "cod_categ": categoria.codigo,
            "dt_inicio": dt_inicio,
            "dependentes": dependentes,
        }
        est_civ = ESTADO_CIVIL.get(employee.marital)
        if est_civ:
            data["est_civ"] = est_civ
        data.update(compl)
        self._registrar_avisos(self._avisos_dependentes(employee, dependentes))
        return data

    def _completar_xml(self, raiz, data):
        ns = {"e": etree.QName(raiz[0]).namespace}
        self._xml_dependentes(raiz.find(".//e:trabalhador", ns), data["dependentes"])
        self._completar_estagiario(raiz, "infoTSVInicio", data.get("estagiario"))

    def _gerar_xml(self):
        return self._montar_xml(self._completar_xml)
