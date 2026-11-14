# Copyright 2024 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""Dados do contracheque: colunas, bases e totais calculados fora do QWeb.

O template só desenha o que este modelo devolve. Assim as regras de quais
rubricas entram em proventos, descontos e informativos, e de qual é a base de
cada tributo, ficam em Python, onde têm teste.
"""
from odoo import api, models

# Categorias cujas linhas não são verba paga ao empregado nem desconto dele.
# GROSS é subtotal (somá-lo duplica os proventos); COMP são os encargos do
# empregador; PROV são as provisões de férias e 13º (passivo estimado, não
# pagamento); NET é o líquido, mostrado à parte.
CATEGORIAS_FORA_DAS_COLUNAS = {"GROSS", "NET", "COMP", "PROV"}
# Rubricas de categoria de verba que o NET não soma: a multa do FGTS é
# depositada pelo empregador na conta vinculada, não é paga no TRCT. Entra como
# informativo para o empregado conferir o valor sem inflar os proventos.
CODIGOS_INFORMATIVOS = {"MULTA_FGTS"}
# Estruturas em que o INSS e o FGTS incidem sobre o bruto do próprio holerite.
ESTRUTURAS_BASE_BRUTO = {"FERIAS"}
ESTRUTURAS_13 = {"13_2PARCELA", "13_SALARIO"}


class ReportHolerite(models.AbstractModel):
    _name = "report.l10n_br_hr_payroll_report.report_holerite"
    _description = "Dados do contracheque"

    @api.model
    def _get_report_values(self, docids, data=None):
        docs = self.env["hr.payslip"].browse(docids)
        return {
            "doc_ids": docids,
            "doc_model": "hr.payslip",
            "docs": docs,
            "contracheque": {slip.id: self.contracheque(slip) for slip in docs},
        }

    @api.model
    def contracheque(self, slip):
        """Proventos, descontos, informativos, bases e totais de um holerite."""
        slip.ensure_one()
        linhas = slip.line_ids.sorted(lambda ln: (ln.sequence, ln.id))
        visiveis = linhas.filtered(lambda ln: ln.appears_on_payslip and ln.total)
        proventos = visiveis.filtered(self._eh_provento)
        descontos = visiveis.filtered(lambda ln: ln.category_id.code == "DED")
        informativos = visiveis.filtered(self._eh_informativo)
        liquido = sum(linhas.filtered(lambda ln: ln.code == "NET").mapped("total"))
        total_proventos = sum(proventos.mapped("total"))
        total_descontos = sum(descontos.mapped("total"))
        return {
            "proventos": proventos,
            "descontos": descontos,
            "informativos": informativos,
            "total_proventos": total_proventos,
            "total_descontos": total_descontos,
            "liquido": liquido,
            "bases": self._bases(slip, linhas),
        }

    @api.model
    def _eh_informativo(self, linha):
        """Informativa: fora das colunas de valor. As bases têm quadro próprio."""
        if linha.code in CODIGOS_INFORMATIVOS:
            return True
        return linha.category_id.code == "INFO" and not linha.code.startswith("BASE_")

    @api.model
    def _eh_provento(self, linha):
        if linha.code in CODIGOS_INFORMATIVOS:
            return False
        codigo = linha.category_id.code
        return codigo not in CATEGORIAS_FORA_DAS_COLUNAS | {"DED", "INFO"}

    @api.model
    def _bases(self, slip, linhas):
        """Bases do contracheque como ``[(rótulo, valor)]``.

        Espelha a base que a regra de cada estrutura usa (``hr_salary_rule``
        da estrutura): quem muda a regra muda esta função junto.
        """

        def v(*codigos):
            return sum(linhas.filtered(lambda ln: ln.code in codigos).mapped("total"))

        def tem(*codigos):
            return bool(linhas.filtered(lambda ln: ln.code in codigos))

        estrutura = slip.struct_id.code
        contrato = slip.contract_id
        bases = []
        if estrutura == "RESCISAO":
            quitado = slip._l10n_br_decimo_pago_ano(contrato)["quitado"]
            decimo = v("DECIMO_RESCISAO") + quitado
            if tem("INSS"):
                bases.append(("Sal. contribuição INSS", v("SALDO_SALARIO")))
            if tem("INSS_13"):
                bases.append(("Base INSS 13º", decimo))
            base_fgts = v("SALDO_SALARIO", "AVISO_PREVIO_INDENIZADO") + max(decimo, 0)
        elif estrutura == "13_1PARCELA":
            base_fgts = v("ADIANTAMENTO_13")
        elif estrutura in ESTRUTURAS_13:
            bases.append(("Base INSS 13º", v("GROSS")))
            base_fgts = max(v("GROSS") - slip.l10n_br_primeira_parcela_13_paga, 0)
        elif estrutura in ESTRUTURAS_BASE_BRUTO:
            if tem("INSS"):
                bases.append(("Sal. contribuição INSS", max(v("GROSS"), 0)))
            base_fgts = max(v("GROSS"), 0)
        else:
            # Mensal: o salário de contribuição soma as férias gozadas na
            # competência (Lei 8.212/91, art. 28), como a regra do INSS.
            sc = max(v("GROSS") - v("FALTAS") - v("DESC_DSR"), 0)
            if tem("INSS", "CONTRIB_RPPS"):
                base_ferias = slip._l10n_br_inss_ferias_competencia(contrato)[0]
                bases.append(("Sal. contribuição INSS", sc + base_ferias))
            base_fgts = sc
        if tem("BASE_IRRF"):
            bases.append(("Base IRRF", v("BASE_IRRF")))
        if tem("BASE_IRRF_13"):
            bases.append(("Base IRRF 13º", v("BASE_IRRF_13")))
        if tem("FGTS", "FGTS_13", "FGTS_AVISO"):
            bases.append(("Base FGTS", base_fgts))
            bases.append(("FGTS do mês", v("FGTS", "FGTS_13", "FGTS_AVISO")))
        return bases
