# Copyright 2026 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

"""Rubricas 1015 e 9221 do adiantamento de férias (TG-152).

- As duas regras são criadas na atualização (arquivo de dados em ``noupdate``, que
  cria o que falta) sem tabela de rubricas gravada; o ``ideTabRubr`` delas é o da
  tabela que a empresa já usa, resolvido na hora de usar. Banco que recebeu uma
  versão anterior desta mudança, em que a instalação gravou ``"1"``, tem o valor
  limpo aqui (``"1"`` gravado conta como a tabela mais usada e leva as próximas
  rubricas para a tabela errada).
- Nas empresas que já enviam S-1010, cria o S-1010 das duas rubricas.
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
    Regra._esocial_configurar_adiantamento_ferias()
