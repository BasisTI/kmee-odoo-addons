# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from unittest import mock

from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged

from odoo.addons.l10n_br_hr_payroll.models.hr_employee import (
    L10N_BR_HR_VERSAO_MINIMA,
    verifica_campo_vat_do_empregado,
)


@tagged("post_install", "-at_install")
class TestVatEmpregado(TransactionCase):
    """O CPF do empregado vem de ``vat`` (l10n_br_hr >= 18.0.1.8.0)."""

    def test_l10n_br_hr_atual_passa_na_verificacao(self):
        self.assertIn("vat", self.env["hr.employee"]._fields)
        verifica_campo_vat_do_empregado(self.env)

    def test_cpf_com_pontuacao_vira_digitos_em_vat(self):
        employee = self.env["hr.employee"].create(
            {"name": "Empregado VAT", "vat": "111.444.777-35"}
        )
        self.assertEqual(employee.vat, "11144477735")

    def test_l10n_br_hr_antigo_falha_com_mensagem_clara(self):
        """Sem ``vat`` no hr.employee, a mensagem diz o que atualizar."""
        campos = type(self.env["hr.employee"])._fields
        with mock.patch.dict(campos):
            del campos["vat"]
            with self.assertRaises(UserError) as erro:
                verifica_campo_vat_do_empregado(self.env)
        mensagem = str(erro.exception)
        self.assertIn("l10n_br_hr", mensagem)
        self.assertIn(L10N_BR_HR_VERSAO_MINIMA, mensagem)
        self.assertIn("vat", self.env["hr.employee"]._fields)

    def _coluna_legada(self, valor):
        """Cria ``hr_employee.cnpj_cpf`` por SQL (o rollback do teste a desfaz)."""
        cr = self.env.cr
        cr.execute("ALTER TABLE hr_employee ADD COLUMN IF NOT EXISTS cnpj_cpf varchar")
        employee = self.env["hr.employee"].create({"name": "Empregado legado"})
        cr.execute(
            "UPDATE hr_employee SET cnpj_cpf = %s WHERE id = %s", (valor, employee.id)
        )

    def test_banco_sem_a_coluna_legada_passa(self):
        self.env.cr.execute("ALTER TABLE hr_employee DROP COLUMN IF EXISTS cnpj_cpf")
        verifica_campo_vat_do_empregado(self.env)

    def test_coluna_legada_vazia_passa(self):
        self._coluna_legada("")
        verifica_campo_vat_do_empregado(self.env)

    def test_coluna_legada_com_cpf_recusa_e_manda_migrar(self):
        self._coluna_legada("111.444.777-35")
        with self.assertRaises(UserError) as erro:
            verifica_campo_vat_do_empregado(self.env)
        mensagem = str(erro.exception)
        self.assertIn("-u l10n_br_hr", mensagem)
        self.assertIn("openupgradelib", mensagem)
        self.assertNotIn("111.444.777-35", mensagem)

    def test_sem_vat_formatted_cnpj_falha_com_a_versao_minima(self):
        campos = type(self.env["hr.employee"])._fields
        with mock.patch.dict(campos):
            del campos["vat_formatted_cnpj"]
            with self.assertRaises(UserError) as erro:
                verifica_campo_vat_do_empregado(self.env)
        self.assertIn("18.0.1.8.0.2", str(erro.exception))
