# Copyright 2026 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""TG-87: tira do banco a visão do campo que o ``l10n_br_esocial`` deixa de ter.

O ``l10n_br_esocial`` 1.2.0 (TG-105) herdava o formulário de ``hr.leave.type``
com o campo ``l10n_br_esocial_salario_maternidade``. Na atualização o campo some
do modelo, mas a visão, cujo arquivo foi apagado, só seria removida no fim: antes
disso o ``l10n_br_hr_holiday`` (que também depende deste módulo) é recarregado e
valida o formulário com a visão órfã, e o ``-u`` aborta. Este módulo é carregado
antes dos dois, então a visão é removida aqui. Idempotente.
"""

import logging

_logger = logging.getLogger(__name__)

VISAO = "hr_leave_type_view_form_esocial"


def migrate(cr, version):
    cr.execute(
        """SELECT id, res_id FROM ir_model_data
            WHERE module = 'l10n_br_esocial' AND name = %s
              AND model = 'ir.ui.view'""",
        (VISAO,),
    )
    linha = cr.fetchone()
    if not linha:
        return
    data_id, view_id = linha
    cr.execute("DELETE FROM ir_ui_view WHERE id = %s", (view_id,))
    cr.execute("DELETE FROM ir_model_data WHERE id = %s", (data_id,))
    _logger.info("TG-87: visão órfã l10n_br_esocial.%s removida", VISAO)
