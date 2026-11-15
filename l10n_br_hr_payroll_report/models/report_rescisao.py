# Copyright 2024 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""Dados do TRCT (Termo de Rescisão do Contrato de Trabalho) e do termo de quitação.

O TRCT segue o leiaute do anexo da Portaria MTE 1.621/2010 (campos numerados).
A Portaria MTP 671/2021 revogou a 1.621/2010 sem publicar outro modelo; o
leiaute segue sendo o de referência da prática de DP e é o que o relatório
reproduz. O mapeamento rubrica -> campo é explícito (``CAMPOS_VERBAS`` e
``CAMPOS_DESCONTOS``) e testado: rubrica sem campo vai para "Outras verbas"
(95) ou "Outros descontos" (115) com a descrição, e nunca some do termo.

Reaproveita a classificação do contracheque (``report_holerite``): o que é
provento, desconto ou informativo não é redecidido aqui.
"""
from datetime import timedelta

from odoo import api, models

# Campos de verba (50-99): número -> rótulo, na ordem do anexo.
ROTULOS_VERBAS = {
    "50": "Saldo de Salário",
    "51": "Comissões",
    "52": "Gratificações",
    "53": "Adicional de Insalubridade",
    "54": "Adicional de Periculosidade",
    "55": "Adicional Noturno",
    "56.1": "H Extras",
    "57": "Gorjetas",
    "58": "Descanso Semanal Remunerado (DSR)",
    "59": "Reflexo do DSR sobre Salário Variável",
    "60": "Multa Art. 477, § 8º/CLT",
    "61": "Multa Art. 479/CLT",
    "62": "Salário-Família",
    "63": "13º Salário Proporcional",
    "64.1": "13º Salário Exercício",
    "65": "Férias Proporcionais",
    "66.1": "Férias Vencidas Per. Aquisitivo",
    "68": "Terço Constitucional de Férias",
    "69": "Aviso-Prévio Indenizado",
    "70": "13º Salário (Aviso-Prévio Indenizado)",
    "71": "Férias (Aviso-Prévio Indenizado)",
    "72": "Percentagem",
    "73": "Prêmios",
    "74": "Viagens",
    "75": "Sobreaviso",
    "76": "Prontidão",
    "77": "Adicional por Tempo de Serviço",
    "78": "Adicional por Transferência de Localidade de Trabalho",
    "79": "Salário Família Excedente ao Valor Legal",
    "80": "Abono/Gratificação de Férias Excedente 20 Dias Salário",
    "81": "Valor Global Diárias para Viagem Excedente 50% Salário",
    "82": "Ajuda de Custo Art. 470/CLT",
    "83": "Etapas Marítimos",
    "84": "Licença-Prêmio Indenizada",
    "85": "Quebra de Caixa",
    "86": "Participação nos Lucros ou Resultados",
    "87": "Indenização a Título de Incentivo à Demissão",
    "88": "Salário Aprendizagem",
    "89": "Abonos Desvinculados do Salário",
    "90": "Ganhos Eventuais Desvinculados do Salário",
    "91": "Reembolso Creche",
    "92": "Reembolso Babá",
    "93": "Gratificação Semestral",
    "94": "Salário do Mês Anterior à Rescisão",
    "95": "Outras Verbas",
    "96": "Indenização Art. 9º, Lei nº 7.238/84",
    "97": "Indenização Férias Escolares",
    "98": "Multa do Art. 476-A, § 5º, da CLT",
    "99": "Ajuste do Saldo Devedor",
}
# Campos de desconto (100-116).
ROTULOS_DESCONTOS = {
    "100": "Pensão Alimentícia",
    "101": "Adiantamento Salarial",
    "102": "Adiantamento de 13º Salário",
    "103": "Aviso-Prévio Indenizado",
    "104": "Indenização Art. 480/CLT",
    "105": "Empréstimo em Consignação",
    "106": "Vale-Transporte",
    "107": "Reembolso do Vale-Transporte",
    "108": "Vale-Alimentação",
    "109": "Reembolso do Vale-Alimentação",
    "110": "Contribuição para o FAPI",
    "111": "Contribuição Sindical Laboral",
    "112.1": "Previdência Social",
    "112.2": "Previdência Social 13º Salário",
    "113": "Contribuição Previdência Complementar",
    "114.1": "IRRF",
    "114.2": "IRRF sobre 13º Salário",
    "114.3": "IRRF sobre Participação nos Lucros ou Resultados",
    "115": "Outros Descontos",
    "116": "Desconto de Valor Líquido de TRCT Quitado Decisão Judicial",
}
CAMPO_OUTRAS_VERBAS = "95"
CAMPO_OUTROS_DESCONTOS = "115"

# Rubrica da rescisão -> campo do anexo. O 13º do aviso indenizado (campo 70)
# ainda vem dentro de ``DECIMO_RESCISAO`` (TG-136): sai inteiro no 63.
CAMPOS_VERBAS = {
    "SALDO_SALARIO": "50",
    "INDENIZACAO_ART_479": "61",
    "DECIMO_RESCISAO": "63",
    "FERIAS_INDENIZADAS": "65",
    "FERIAS_VENCIDAS": "66.1",
    "ADICIONAL_FERIAS_INDENIZADAS": "68",
    "ADICIONAL_FERIAS_VENCIDAS": "68",
    "AVISO_PREVIO_INDENIZADO": "69",
}
CAMPOS_DESCONTOS = {
    "PENSAO_ALIMENTICIA": "100",
    "PENSAO_ALIMENTICIA_13": "100",
    "ADIANTAMENTO_13": "102",
    "DESCONTO_AVISO_PREVIO": "103",
    "DESCONTO_ART_480": "104",
    "INSS": "112.1",
    "INSS_13": "112.2",
    "IRRF": "114.1",
    "IRRF_13": "114.2",
}


def _chave(campo):
    """Ordem numérica dos campos: ``"56.1"`` vem depois de ``"55"``."""
    inteiro, _sep, fracao = campo.partition(".")
    return int(inteiro), int(fracao or 0)


class ReportTermoRescisao(models.AbstractModel):
    _name = "report.l10n_br_hr_payroll_report.report_termo_rescisao"
    _description = "Dados do TRCT e do termo de quitação"

    @api.model
    def _get_report_values(self, docids, data=None):
        docs = self.env["hr.payslip"].browse(docids)
        return {
            "doc_ids": docids,
            "doc_model": "hr.payslip",
            "docs": docs,
            "trct": {slip.id: self.trct(slip) for slip in docs},
        }

    @api.model
    def _agrupar(self, linhas, mapa, rotulos, campo_outros):
        """Soma as linhas por campo e devolve ``(valores, outros)``.

        ``valores`` é ``{campo: total}``; ``outros`` lista, por rubrica sem
        campo, ``(descrição, valor)``, que também entra no total do campo de
        "outras" para o termo fechar.
        """
        valores = {}
        outros = []
        for linha in linhas:
            campo = mapa.get(linha.code)
            if campo is None:
                campo = campo_outros
                outros.append((linha.name, linha.total))
            valores[campo] = round(valores.get(campo, 0.0) + linha.total, 2)
        return valores, outros

    @api.model
    def _dados_empregador(self, slip):
        empresa = slip.company_id
        partner = empresa.partner_id
        return {
            "cnpj": empresa.vat or "",
            "razao_social": empresa.name or "",
            "logradouro": ", ".join(p for p in (partner.street, partner.street2) if p),
            "municipio": partner.city or "",
            "uf": partner.state_id.code or "",
            "cep": partner.zip or "",
        }

    @api.model
    def _dados_trabalhador(self, slip):
        emp = slip.employee_id
        return {
            "pis": emp.pis_pasep or "",
            "nome": emp.name or "",
            "logradouro": emp.private_street or "",
            "municipio": emp.private_city or "",
            "uf": emp.private_state_id.code or "",
            "cep": emp.private_zip or "",
            "ctps": emp.ctps or "",
            "ctps_serie": emp.ctps_series or "",
            "cpf": emp.cnpj_cpf or "",
            "nascimento": emp.birthday,
            "mae": emp.mother_name or "",
        }

    @api.model
    def _data_aviso(self, slip):
        """Data do aviso prévio: a do afastamento no indenizado; o início do
        período trabalhado no trabalhado. Sem aviso, em branco."""
        aviso = slip.l10n_br_aviso_previo
        if aviso == "indenizado":
            return slip.date_to
        if aviso == "trabalhado":
            dias = slip._l10n_br_dias_aviso_previo()
            return slip.date_to - timedelta(days=max(dias - 1, 0))
        return False

    @api.model
    def _dados_contrato(self, slip):
        contrato = slip.contract_id
        tipo = slip.l10n_br_tipo_rescisao
        selecao = dict(slip._fields["l10n_br_tipo_rescisao"].selection)
        prazo_determinado = bool(slip.l10n_br_data_termo_contrato) or tipo in (
            "termino_contrato",
            "antecipado_empregador",
            "antecipado_empregado",
        )
        sindicato = (
            contrato.partner_union if "partner_union" in contrato._fields else None
        )
        return {
            "sindicato": " - ".join(p for p in (sindicato.vat, sindicato.name) if p)
            if sindicato
            else "",
            "tipo_contrato": "Prazo determinado"
            if prazo_determinado
            else "Prazo indeterminado",
            "causa": selecao.get(tipo, ""),
            "remuneracao": contrato.wage,
            "admissao": contrato.date_start,
            "aviso": self._data_aviso(slip),
            "afastamento": slip.date_to,
            "codigo_afastamento": slip._l10n_br_motivo_desligamento_esocial() or "",
            "pensao_trct": slip.employee_id.l10n_br_pensao_percentual,
            # O cadastro só tem um percentual de pensão; o do saque do FGTS
            # (campo 29) é decisão judicial própria e fica em branco.
            "pensao_fgts": 0.0,
            "categoria": dict(
                slip.employee_id._fields["l10n_br_tipo_contrato"].selection
            ).get(slip.employee_id.l10n_br_tipo_contrato, ""),
        }

    @api.model
    def trct(self, slip):
        """Campos do TRCT, verbas, descontos, totais e líquido de uma rescisão."""
        slip.ensure_one()
        holerite = self.env["report.l10n_br_hr_payroll_report.report_holerite"]
        contracheque = holerite.contracheque(slip)
        verbas, outras_verbas = self._agrupar(
            contracheque["proventos"],
            CAMPOS_VERBAS,
            ROTULOS_VERBAS,
            CAMPO_OUTRAS_VERBAS,
        )
        descontos, outros_descontos = self._agrupar(
            contracheque["descontos"],
            CAMPOS_DESCONTOS,
            ROTULOS_DESCONTOS,
            CAMPO_OUTROS_DESCONTOS,
        )
        avos = {"63": slip.l10n_br_avos_13, "65": slip.l10n_br_avos_ferias}
        return {
            "empregador": self._dados_empregador(slip),
            "trabalhador": self._dados_trabalhador(slip),
            "contrato": self._dados_contrato(slip),
            "verbas": [
                (campo, rotulo, verbas.get(campo, 0.0), avos.get(campo))
                for campo, rotulo in ROTULOS_VERBAS.items()
            ],
            "descontos": [
                (campo, rotulo, descontos.get(campo, 0.0), None)
                for campo, rotulo in ROTULOS_DESCONTOS.items()
            ],
            "outras_verbas": outras_verbas,
            "outros_descontos": outros_descontos,
            "informativos": contracheque["informativos"],
            "total_bruto": contracheque["total_proventos"],
            "total_deducoes": contracheque["total_descontos"],
            "liquido": contracheque["liquido"],
            "bases": contracheque["bases"],
        }
