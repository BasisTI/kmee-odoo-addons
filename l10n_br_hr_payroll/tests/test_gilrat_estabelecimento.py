# Copyright 2024 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""RAT/FAP por estabelecimento, com vigência (TG-122).

Os FAPs de 2026 são os da story (S-5011 da Basis): matriz 1,2262; filiais 0003,
0004 e 0005 com 0,5; 0007 com 1,0; 0006 com 1,5289. O RAT é 3% em todas e o
salário, R$ 6.000,00 (competência 03/2026), para o RAT sair conferível à mão.
"""
from datetime import date

from odoo.exceptions import ValidationError
from odoo.tests import tagged

from .test_encargos_patronais import EncargosPatronaisCommon

RAIZ = "12345678"
FAP_2026 = {
    "0001": 1.2262,
    "0003": 0.5,
    "0004": 0.5,
    "0005": 0.5,
    "0006": 1.5289,
    "0007": 1.0,
}


INI_2026 = date(2026, 1, 1)
FIM_2026 = date(2026, 12, 31)


def cnpj_valido(raiz, ordem):
    """CNPJ de 14 dígitos com os verificadores corretos."""
    base = raiz + ordem
    for pesos in (
        [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2],
        [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2],
    ):
        soma = sum(int(d) * p for d, p in zip(base, pesos))
        resto = soma % 11
        base += "0" if resto < 2 else str(11 - resto)
    return base


@tagged("post_install", "-at_install")
class TestGilratEstabelecimento(EncargosPatronaisCommon):
    def setUp(self):
        super().setUp()
        self._config_empresa(tax_framework="3", rat="3", fap=1.0)
        self.env.company.partner_id.vat = cnpj_valido(RAIZ, "0001")
        self.Gilrat = self.env["l10n_br.hr.payroll.gilrat"]

    def _gilrat(self, ordem, fap, ini=INI_2026, fim=FIM_2026):
        return self.Gilrat.create(
            {
                "company_id": self.env.company.id,
                "cnpj": self._cnpj(ordem),
                "date_start": ini,
                "date_end": fim,
                "rat": "3",
                "fap": fap,
            }
        )

    def _cnpj(self, ordem):
        return cnpj_valido(RAIZ, ordem)

    def _holerite_no_estabelecimento(self, ordem, date_from=None, date_to=None):
        """Holerite de empregado cujo Endereço de Trabalho é a filial ``ordem``."""
        Partner = self.env["res.partner"]
        partner = Partner.search([("vat", "=", self._cnpj(ordem))], limit=1)
        if not partner:
            partner = Partner.create(
                {"name": "Filial %s" % ordem, "vat": self._cnpj(ordem)}
            )
        emp = self._create_employee()
        emp.address_id = partner
        contract = self._create_contract(emp, wage=6000.0)
        return self._create_payslip(
            emp,
            contract,
            date_from=date_from or date(2026, 3, 1),
            date_to=date_to or date(2026, 3, 31),
        )

    def test_rat_de_cada_estabelecimento_pelo_fap_da_story(self):
        """O RAT de cada filial usa o FAP dela, não o da empresa."""
        for sufixo, fap in FAP_2026.items():
            self._gilrat(sufixo, fap)
        for sufixo, fap in FAP_2026.items():
            payslip = self._holerite_no_estabelecimento(sufixo)
            self.assertAlmostEqualMoney(
                self._get_line_total(payslip, "RAT"),
                round(6000.0 * 0.03 * fap, 2),
                msg="RAT do estabelecimento %s (FAP %s)" % (sufixo, fap),
            )

    def test_vigencia_fap_muda_todo_ano(self):
        """A regra pega a linha vigente na competência do holerite."""
        self._gilrat("0003", 0.9, ini=date(2025, 1, 1), fim=date(2025, 12, 31))
        self._gilrat("0003", 0.5)
        p2026 = self._holerite_no_estabelecimento("0003")
        p2025 = self._holerite_no_estabelecimento(
            "0003", date(2025, 3, 1), date(2025, 3, 31)
        )
        self.assertAlmostEqualMoney(self._get_line_total(p2026, "RAT"), 90.0)
        self.assertAlmostEqualMoney(self._get_line_total(p2025, "RAT"), 162.0)

    def test_sem_linha_cai_no_valor_da_empresa(self):
        """Estabelecimento sem linha na competência usa RAT/FAP da empresa."""
        self.env.company.l10n_br_hr_fap = 1.2262
        self._gilrat("0003", 0.5, ini=date(2027, 1, 1), fim=date(2027, 12, 31))
        payslip = self._holerite_no_estabelecimento("0003")
        self.assertAlmostEqualMoney(self._get_line_total(payslip, "RAT"), 220.72)
        sem_filial = self._holerite()
        self.assertAlmostEqualMoney(self._get_line_total(sem_filial, "RAT"), 220.72)

    def test_vigencia_sobreposta_e_recusada(self):
        self._gilrat("0004", 0.5)
        with self.assertRaises(ValidationError):
            self._gilrat("0004", 0.8, ini=date(2026, 6, 1), fim=date(2027, 5, 31))
        # outro estabelecimento no mesmo período é livre
        self._gilrat("0005", 0.8)

    def test_fap_e_vigencia_validados(self):
        with self.assertRaises(ValidationError):
            self._gilrat("0004", 2.5)
        with self.assertRaises(ValidationError):
            self._gilrat("0004", 1.0, ini=date(2026, 1, 15))
        with self.assertRaises(ValidationError):
            self._gilrat("0004", 1.0, fim=date(2026, 12, 30))

    def test_trocar_cnpj_ou_empresa_revalida_sobreposicao(self):
        """Editar CNPJ/empresa para colidir com outra vigência é recusado."""
        self._gilrat("0004", 0.5)
        outra = self._gilrat("0005", 0.8)
        with self.assertRaises(ValidationError):
            outra.cnpj = self._cnpj("0004")
        # a mesma linha em outra empresa não colide; voltar a colidir, sim
        filha = self.env["res.company"].create({"name": "Filha TG-122 gilrat"})
        filha.partner_id.vat = cnpj_valido(RAIZ, "0002")
        outra.company_id = filha
        with self.assertRaises(ValidationError):
            outra.write({"company_id": self.env.company.id, "cnpj": self._cnpj("0004")})

    def test_cnpj_valido_e_da_raiz_do_empregador(self):
        with self.assertRaises(ValidationError):
            self.Gilrat.create(
                {
                    "cnpj": "12345678000300",  # dígito verificador errado
                    "date_start": INI_2026,
                    "rat": "3",
                    "fap": 1.0,
                }
            )
        with self.assertRaises(ValidationError):
            self.Gilrat.create(
                {
                    "cnpj": cnpj_valido("11222333", "0001"),  # outra raiz
                    "date_start": INI_2026,
                    "rat": "3",
                    "fap": 1.0,
                }
            )
        with self.assertRaises(ValidationError):
            self._gilrat("0004", 1.0).cnpj = cnpj_valido("11222333", "0001")

    def test_formulario_da_empresa_sem_erro_para_usuario_sem_folha(self):
        """O bloco novo é só do grupo de folha: sem ele, sem AccessError."""
        user = self.env["res.users"].create(
            {
                "name": "Sem folha",
                "login": "sem_folha_gilrat",
                "groups_id": [(6, 0, [self.env.ref("base.group_user").id])],
                "company_ids": [(6, 0, [self.env.company.id])],
                "company_id": self.env.company.id,
            }
        )
        company = self.env.company.with_user(user)
        arch = company.get_view(self.env.ref("base.view_company_form").id)["arch"]
        self.assertNotIn("l10n_br_hr_gilrat_ids", arch)
        company.read(["name"])
        gerente = self.env["res.users"].create(
            {
                "name": "Folha",
                "login": "folha_gilrat",
                "groups_id": [
                    (6, 0, [self.env.ref("payroll.group_payroll_manager").id])
                ],
                "company_ids": [(6, 0, [self.env.company.id])],
                "company_id": self.env.company.id,
            }
        )
        arch = self.env.company.with_user(gerente).get_view(
            self.env.ref("base.view_company_form").id
        )["arch"]
        self.assertIn("l10n_br_hr_gilrat_ids", arch)
