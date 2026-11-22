# Copyright 2026 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""TG-159: o DSR_HE reflete toda hora extra (categoria HE), não só HE_50 e HE_100.

Os dados são ``noupdate="1"``: o ``-u`` não os troca em banco instalado. Aqui:

- cria a categoria ``HE`` (filha de ``ALW``) se não existir;
- ``HE_50`` e ``HE_100`` passam para ela só se ainda estão em ``ALW``;
- ``DSR_HE`` passa a ler ``categories.HE`` só se a condição e a fórmula gravadas
  forem exatamente as da 1.13.0 (regra personalizada fica como está, com aviso).

Idempotente; holerite já calculado não muda, o em rascunho recalcula.
"""
import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)

CONDICAO_1_13 = "result = (HE_50 + HE_100) > 0"
FORMULA_1_13 = "result = tools.br.dsr_reflexo(HE_50 + HE_100)"
CONDICAO_NOVA = "result = categories.HE > 0"
FORMULA_NOVA = "result = tools.br.dsr_reflexo(categories.HE)"


def _normaliza(texto):
    return "\n".join(
        linha.strip() for linha in (texto or "").strip().splitlines() if linha.strip()
    )


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    alw = env.ref("l10n_br_hr_payroll.hr_salary_rule_category_alw", False)
    if not alw:
        return
    he = env.ref("l10n_br_hr_payroll.hr_salary_rule_category_he", False)
    if not he:
        he = env["hr.salary.rule.category"].create(
            {"name": "Horas Extras", "code": "HE", "parent_id": alw.id}
        )
        env["ir.model.data"].create(
            {
                "name": "hr_salary_rule_category_he",
                "module": "l10n_br_hr_payroll",
                "model": "hr.salary.rule.category",
                "res_id": he.id,
                "noupdate": True,
            }
        )
    for xmlid in ("hr_rule_he_50", "hr_rule_he_100"):
        regra = env.ref(f"l10n_br_hr_payroll.{xmlid}", False)
        if regra and regra.category_id == alw:
            regra.category_id = he
    dsr = env.ref("l10n_br_hr_payroll.hr_rule_dsr_he", False)
    if not dsr:
        return
    if _normaliza(dsr.condition_python) == CONDICAO_NOVA:
        return
    if (
        dsr.condition_select == "python"
        and _normaliza(dsr.condition_python) == CONDICAO_1_13
        and _normaliza(dsr.amount_python_compute) == FORMULA_1_13
    ):
        dsr.write(
            {"condition_python": CONDICAO_NOVA, "amount_python_compute": FORMULA_NOVA}
        )
        _logger.info("TG-159: DSR_HE passou a refletir a categoria HE")
    else:
        _logger.warning(
            "TG-159: DSR_HE personalizada, não foi trocada; ajuste para categories.HE"
        )
