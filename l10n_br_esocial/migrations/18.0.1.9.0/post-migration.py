# Copyright 2026 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

"""IR do recibo de férias que atravessa o mês (TG-152, rodada 4).

Vale também para o banco que já está na 18.0.1.8.0 (a migração 1.8.0 não roda de
novo nele):

- limpa o ``"1"`` gravado em ``ideTabRubr`` das rubricas 1015/9221 por uma versão
  anterior (``"1"`` gravado conta como a tabela mais usada da empresa e leva as
  próximas rubricas para a tabela errada);
- o desconto do adiantamento (9221) passa a ``codIncIRRF`` 09 (o 1015 é bruto, e o
  9221 das competências seguintes não tem efeito no IR); o arquivo de dados é
  ``noupdate`` e não reescreve a regra já criada;
- a provisão de CP (9201, IRRF 43) é criada pelo arquivo de dados; aqui sai o
  S-1010 dela nas empresas que já enviam S-1010.
"""

from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    Regra = env["hr.salary.rule"]
    regras = Regra._esocial_regras_adiantamento_ferias()
    regras.filtered(lambda regra: regra.l10n_br_esocial_ide_tab_rubr == "1").write(
        {"l10n_br_esocial_ide_tab_rubr": False}
    )
    for xmlid in (
        "l10n_br_esocial.hr_rule_desconto_adiantamento_ferias",
        "l10n_br_esocial.hr_rule_desconto_adiantamento_abono",
    ):
        regra = env.ref(xmlid, raise_if_not_found=False)
        if regra and regra.l10n_br_esocial_cod_inc_irrf != "09":
            regra.write({"l10n_br_esocial_cod_inc_irrf": "09"})
    Regra._esocial_configurar_adiantamento_ferias()
