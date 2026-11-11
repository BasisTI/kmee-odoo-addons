# Copyright 2026 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""TG-107: as tabelas de incidência do módulo são as do leiaute S-1.3.

Compara o que o módulo oferece (listas de seleção da regra salarial e a tabela 21
carregada do CSV) com a cópia oficial em ``leiaute_s13.py`` e acusa código a mais,
código a menos e descrição ou validade divergente.
"""

import csv
import importlib.util
from datetime import date

from odoo.tests.common import TransactionCase
from odoo.tools import file_path

from odoo.addons.l10n_br_esocial.models.hr_salary_rule import (
    ESOCIAL_COD_INC_CP,
    ESOCIAL_COD_INC_FGTS,
    ESOCIAL_COD_INC_IRRF,
)

from . import leiaute_s13


def _rotulo(codigo, grupo, descricao):
    return f"{codigo} - {grupo} - {descricao}" if grupo else f"{codigo} - {descricao}"


def _chave_irrf(codigo):
    """Seleção do IRRF guarda 09 com dois dígitos; os demais como o leiaute."""
    return "%02d" % int(codigo) if int(codigo) < 10 else str(int(codigo))


def diferencas(encontrado, esperado):
    """Lista as diferenças entre dois ``{código: valor}``."""
    problemas = []
    for codigo in sorted(set(esperado) - set(encontrado)):
        problemas.append(f"falta o código {codigo}: {esperado[codigo]!r}")
    for codigo in sorted(set(encontrado) - set(esperado)):
        problemas.append(
            f"código {codigo} a mais, fora do leiaute: {encontrado[codigo]!r}"
        )
    for codigo in sorted(set(encontrado) & set(esperado)):
        if encontrado[codigo] != esperado[codigo]:
            problemas.append(
                f"código {codigo} diverge: módulo {encontrado[codigo]!r}, "
                f"leiaute {esperado[codigo]!r}"
            )
    return problemas


def _esperado_selecao(linhas):
    return {c: _rotulo(c, g, d) for c, g, d in linhas}


def _esperado_irrf_selecao():
    return {
        _chave_irrf(c): _rotulo(_chave_irrf(c), g, d)
        for c, g, d, _inicio, fim in leiaute_s13.INCIDENCIA_IRRF
        if not fim
    }


class TestTabelasIncidencia(TransactionCase):
    def test_selecao_inss(self):
        self.assertEqual(
            diferencas(
                dict(ESOCIAL_COD_INC_CP), _esperado_selecao(leiaute_s13.INCIDENCIA_CP)
            ),
            [],
        )

    def test_selecao_fgts(self):
        self.assertEqual(
            diferencas(
                dict(ESOCIAL_COD_INC_FGTS),
                _esperado_selecao(leiaute_s13.INCIDENCIA_FGTS),
            ),
            [],
        )

    def test_selecao_irrf_so_codigos_vigentes(self):
        self.assertEqual(
            diferencas(dict(ESOCIAL_COD_INC_IRRF), _esperado_irrf_selecao()), []
        )

    def test_campos_da_regra_usam_as_listas(self):
        campos = self.env["hr.salary.rule"]._fields
        for campo, lista in (
            ("l10n_br_esocial_cod_inc_cp", ESOCIAL_COD_INC_CP),
            ("l10n_br_esocial_cod_inc_irrf", ESOCIAL_COD_INC_IRRF),
            ("l10n_br_esocial_cod_inc_fgts", ESOCIAL_COD_INC_FGTS),
        ):
            self.assertEqual(campos[campo].selection, lista, campo)

    def test_tabela_21_carregada_e_a_do_leiaute(self):
        """Todos os 87 códigos da Tabela 21, com descrição e validade."""
        registros = self.env["l10n_br.esocial.incidencia.irrf"].search_read(
            [("active", "in", (True, False))], ["codigo", "nome", "dt_inicio", "dt_fim"]
        )
        encontrado = {
            str(int(r["codigo"])): (r["nome"], r["dt_inicio"], r["dt_fim"] or None)
            for r in registros
        }
        esperado = {
            str(int(c)): (
                d,
                date.fromisoformat(inicio),
                date.fromisoformat(fim) if fim else None,
            )
            for c, _g, d, inicio, fim in leiaute_s13.INCIDENCIA_IRRF
        }
        self.assertEqual(diferencas(encontrado, esperado), [])

    def test_csv_de_incidencia_irrf_confere_com_o_leiaute(self):
        """O CSV (o que vai para bancos novos) também é a Tabela 21."""
        with open(
            file_path("l10n_br_esocial/data/l10n_br.esocial.incidencia.irrf.csv"),
            encoding="utf-8",
        ) as arquivo:
            encontrado = {
                str(int(r["codigo"])): (r["nome"], r["dt_inicio"], r["dt_fim"])
                for r in csv.DictReader(arquivo)
            }
        esperado = {
            str(int(c)): (d, inicio, fim)
            for c, _g, d, inicio, fim in leiaute_s13.INCIDENCIA_IRRF
        }
        self.assertEqual(diferencas(encontrado, esperado), [])

    def test_rubrica_padrao_so_usa_codigos_do_leiaute(self):
        """``cod_inc_*`` da rubrica padrão existem nas tabelas (``0`` é o ``00``)."""
        validos = {
            "cod_inc_cp": {str(int(c)) for c, _g, _d in leiaute_s13.INCIDENCIA_CP},
            "cod_inc_fgts": {str(int(c)) for c, _g, _d in leiaute_s13.INCIDENCIA_FGTS},
            "cod_inc_irrf": {
                str(int(c)) for c, _g, _d, _i, _f in leiaute_s13.INCIDENCIA_IRRF
            },
        }
        invalidos = []
        for rubrica in self.env["l10n_br.esocial.rubrica.padrao"].search([]):
            for campo, codigos in validos.items():
                valor = rubrica[campo]
                if valor and str(int(valor)) not in codigos:
                    invalidos.append((rubrica.codigo, campo, valor))
        self.assertEqual(invalidos, [])

    def test_migracao_conhece_os_mesmos_codigos(self):
        """A lista da migração 18.0.1.2.0 é a das seleções."""
        caminho = file_path("l10n_br_esocial/migrations/18.0.1.2.0/post-migration.py")
        spec = importlib.util.spec_from_file_location("migracao_tg107", caminho)
        migracao = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(migracao)
        for campo, lista in (
            ("l10n_br_esocial_cod_inc_cp", ESOCIAL_COD_INC_CP),
            ("l10n_br_esocial_cod_inc_irrf", ESOCIAL_COD_INC_IRRF),
            ("l10n_br_esocial_cod_inc_fgts", ESOCIAL_COD_INC_FGTS),
        ):
            self.assertEqual(migracao.VALIDOS[campo], {c for c, _ in lista}, campo)

    def test_o_teste_acusa_diferenca(self):
        """Código a mais, a menos e descrição divergente são apontados."""
        esperado = _esperado_selecao(leiaute_s13.INCIDENCIA_FGTS)
        adulterado = dict(esperado)
        adulterado.pop("31")
        adulterado["99"] = "99 - Inventado"
        adulterado["21"] = "21 - Sal. Maternidade"
        problemas = diferencas(adulterado, esperado)
        self.assertEqual(len(problemas), 3)
        self.assertTrue(any("falta o código 31" in p for p in problemas))
        self.assertTrue(any("código 99 a mais" in p for p in problemas))
        self.assertTrue(any("código 21 diverge" in p for p in problemas))
