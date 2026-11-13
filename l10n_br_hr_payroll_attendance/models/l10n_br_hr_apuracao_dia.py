# Copyright 2026 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import models


class L10nBrHrApuracaoDia(models.Model):
    _inherit = "l10n_br.hr.apuracao.dia"

    def _usa_hora_reduzida(self):
        """A hora reduzida segue o contrato (TG-128).

        Contrato sem direito (rural, convenção) apura o noturno pelo relógio;
        sem contrato na apuração, vale o padrão urbano (art. 73, § 1º).
        """
        contrato = self.contract_id
        if contrato:
            return contrato.l10n_br_hora_noturna_reduzida
        return super()._usa_hora_reduzida()
