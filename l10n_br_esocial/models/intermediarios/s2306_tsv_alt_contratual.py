# Copyright 2026 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import _, fields, models


class ESocialS2306(models.Model):
    _name = "l10n_br.esocial.s2306"
    _inherit = "l10n_br.esocial.tsv.mixin"
    _description = "eSocial S-2306 - Trabalhador sem vínculo - Alteração contratual"

    dt_alteracao = fields.Date(string="Data da Alteração", required=True)

    def _get_event_type(self):
        return "S-2306"

    def _get_dt_alteracao(self, contract, employee):
        if contract.date_start and self.dt_alteracao < contract.date_start:
            self._erro_cadastro(
                _(
                    "Contrato '%(name)s': a data da alteração (%(dt)s) é anterior "
                    "ao início do contrato."
                ),
                name=contract.display_name,
                dt=self.dt_alteracao,
            )
        return str(self.dt_alteracao)

    def _to_esociallib_dict(self):
        """Dict do S-2306, ou ``UserError`` com TODOS os dados que faltam."""
        self.ensure_one()
        employee = self.employee_id
        contract = self.contract_id
        erros = []
        cpf, matricula, categoria, ide = self._identificar(erros, "S-2306")
        proc = self._get_proc_info()
        dt_alteracao = self._coletar(erros, self._get_dt_alteracao, contract, employee)
        compl = self._dados_complementares(
            erros,
            categoria,
            ide,
            str(contract.date_start) if contract.date_start else "",
        )
        if erros:
            self._erro_evento("S-2306", erros)
        data = {
            "tp_insc": ide["tp_insc"],
            "nr_insc": ide["nr_insc"],
            "proc_emi": proc["proc_emi"],
            "ver_proc": proc["ver_proc"],
            "cpf_trab": cpf,
            "matricula": matricula,
            "cod_categ": categoria.codigo,
            "dt_alteracao": dt_alteracao,
        }
        data.update(compl)
        return data

    def _completar_xml(self, raiz, data):
        self._completar_estagiario(raiz, "infoTSVAlteracao", data.get("estagiario"))

    def _gerar_xml(self):
        return self._montar_xml(self._completar_xml)
