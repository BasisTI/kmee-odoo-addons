# Copyright 2024 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import logging
from datetime import date

from odoo import _, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

# MOS S-1.3, S-2230, itens 4.1 e 5.1: o acidente/doença do trabalho (motivo 01) é
# informado desde o 1º dia, qualquer que seja a duração. A doença não relacionada
# ao trabalho (motivo 03) é obrigatória só acima de 15 dias, na recaída pela mesma
# doença em 60 dias (soma acima de 15, ou em até 60 dias do retorno de um
# afastamento acima de 15); nas demais hipóteses a informação é opcional. Os
# motivos 02 e 04 foram encerrados em 2016-12-31.
MOTIVO_TRABALHO = "01"
MOTIVO_DOENCA = "03"
DIAS_EMPRESA = 15
# Item 5.2: a janela de 60 dias conta do término do primeiro afastamento.
DIAS_RECAIDA = 60
# Leiaute S-1.3 (NT 07/2026), S-2230, ``infoMesmoMtv`` (em ``iniAfastamento``):
# exclusivo dos motivos 01 e 03 e exigido a partir de 2026-10-26. Com outro
# afastamento do mesmo motivo nos 60 dias anteriores, o evento informa S (mesma
# doença/acidente) ou N; sem anterior, o campo fica vazio ou vale N.
INICIO_INFO_MESMO_MTV = date(2026, 10, 26)
MOTIVOS_INFO_MESMO_MTV = (MOTIVO_TRABALHO, MOTIVO_DOENCA)


def _dias(inicio, fim):
    return (fim - inicio).days + 1


class ESocialS2230(models.Model):
    _name = "l10n_br.esocial.s2230"
    _inherit = "l10n_br.esocial.base.intermediario"
    _description = "eSocial S-2230 - Afastamento Temporário"

    employee_id = fields.Many2one(
        "hr.employee",
        string="Empregado",
        required=True,
        ondelete="cascade",
    )
    dt_ini_afast = fields.Date(
        string="Data Início Afastamento",
    )
    dt_term_afast = fields.Date(
        string="Data Término Afastamento",
    )
    cod_mot_afast = fields.Char(
        string="Código Motivo Afastamento",
        size=2,
        help="Código conforme Tabela 18 do eSocial.",
    )
    motivo_afastamento_id = fields.Many2one(
        "l10n_br.esocial.motivo.afastamento",
        string="Motivo Afastamento",
    )

    info_mesmo_mtv = fields.Selection(
        [
            ("S", "Sim, mesma doença/acidente do afastamento anterior"),
            ("N", "Não, outra doença/acidente"),
        ],
        string="Mesmo motivo do afastamento anterior",
        help="Leiaute S-1.3 (a partir de 26/10/2026), motivos 01 e 03: quando há "
        "outro afastamento do mesmo motivo nos 60 dias anteriores, informe se "
        "decorre da mesma doença/acidente (S) ou não (N). O afastamento do Odoo "
        "não tem CID, então a informação vem do usuário.",
    )

    def _get_event_type(self):
        return "S-2230"

    informar_opcional = fields.Boolean(
        string="Informar mesmo sem obrigatoriedade",
        help="Doença não relacionada ao trabalho de até 15 dias, fora de recaída, "
        "é de informação opcional no eSocial: marque para gerar o evento assim "
        "mesmo.",
    )

    def _afastamentos_inss(self):
        """Períodos ``(inicio, fim)`` de doença do empregado, ordenados.

        Mesmo critério da TG-82 (tipo com ``l10n_br_afastamento_inss``). Acidente
        do trabalho (com S-2230 de motivo 01 no mesmo início) não soma com a
        doença comum.
        """
        self.ensure_one()
        leaves = (
            self.env["hr.leave"]
            .sudo()
            .search(
                [
                    ("employee_id", "=", self.employee_id.id),
                    ("state", "=", "validate"),
                    ("holiday_status_id.l10n_br_afastamento_inss", "=", True),
                ],
                order="request_date_from",
            )
        )
        acidentes = {
            s.dt_ini_afast
            for s in self.sudo().search(
                [
                    ("employee_id", "=", self.employee_id.id),
                    ("cod_mot_afast", "=", MOTIVO_TRABALHO),
                ]
            )
        } | {
            s.dt_ini_afast
            for s in self.sudo().search(
                [
                    ("employee_id", "=", self.employee_id.id),
                    ("motivo_afastamento_id.codigo", "=", MOTIVO_TRABALHO),
                ]
            )
        }
        return [
            (lv.request_date_from, lv.request_date_to)
            for lv in leaves
            if lv.request_date_from not in acidentes
        ]

    def _cadeias_recaida(self, periodos):
        """Agrupa os períodos em cadeias de recaída (item 5.2 do MOS).

        Cada cadeia começa num afastamento e leva os seguintes que começam em até
        60 dias do término desse primeiro.
        """
        cadeias = []
        for periodo in sorted(periodos):
            if cadeias and (periodo[0] - cadeias[-1][0][1]).days <= DIAS_RECAIDA:
                cadeias[-1].append(periodo)
            else:
                cadeias.append([periodo])
        return cadeias

    def _periodo_devido(self, inicio, fim):
        """Doença (motivo 03) de ``inicio`` a ``fim`` é de informação obrigatória?"""
        self.ensure_one()
        if _dias(inicio, fim) > DIAS_EMPRESA:
            return True
        periodos = {p for p in self._afastamentos_inss() if p[0] != inicio}
        periodos.add((inicio, fim))
        for cadeia in self._cadeias_recaida(periodos):
            if (inicio, fim) in cadeia and sum(
                _dias(*p) for p in cadeia
            ) > DIAS_EMPRESA:
                return True
        # Até 60 dias do retorno de um afastamento acima de 15 dias.
        return any(
            _dias(*p) > DIAS_EMPRESA and 0 < (inicio - p[1]).days <= DIAS_RECAIDA
            for p in periodos
        )

    def _recaida_sem_evento(self):
        """Afastamentos da cadeia de recaída deste, obrigatórios e sem S-2230.

        O MOS manda informar cada afastamento da cadeia no seu evento. O módulo
        não os gera sozinho (nem recusa o evento atual por falta deles): use
        ``action_gerar_recaida_pendente``.
        """
        self.ensure_one()
        if not self.dt_ini_afast or not self.dt_term_afast:
            return []
        periodos = set(self._afastamentos_inss())
        periodos.add((self.dt_ini_afast, self.dt_term_afast))
        existentes = {
            s.dt_ini_afast
            for s in self.sudo().search(
                [("employee_id", "=", self.employee_id.id), ("id", "!=", self.id)]
            )
        }
        pendentes = []
        for cadeia in self._cadeias_recaida(periodos):
            if (self.dt_ini_afast, self.dt_term_afast) not in cadeia:
                continue
            if sum(_dias(*p) for p in cadeia) > DIAS_EMPRESA:
                pendentes = [
                    p
                    for p in cadeia
                    if p[0] != self.dt_ini_afast and p[0] not in existentes
                ]
        return pendentes

    def action_gerar_recaida_pendente(self, info_mesmo_mtv=None):
        """Cria os S-2230 (motivo 03) que faltam na cadeia de recaída deste.

        Os pendentes nascem com ``info_mesmo_mtv`` (S ou N). Quando o leiaute exige
        o campo (início a partir de 2026-10-26 e anterior em 60 dias), a ação
        recusa sem o valor em vez de criar eventos que a geração recusaria.
        """
        self.ensure_one()
        if info_mesmo_mtv not in (None, False, "S", "N"):
            raise UserError(_("info_mesmo_mtv deve ser 'S' ou 'N'."))
        motivo = self.motivo_afastamento_id or self.env[
            "l10n_br.esocial.motivo.afastamento"
        ].search([("codigo", "=", MOTIVO_DOENCA)], limit=1)
        criados = self.create(
            [
                {
                    "employee_id": self.employee_id.id,
                    "company_id": self.company_id.id,
                    "dt_ini_afast": ini,
                    "dt_term_afast": fim,
                    "cod_mot_afast": self.cod_mot_afast,
                    "motivo_afastamento_id": motivo.id,
                    "info_mesmo_mtv": info_mesmo_mtv or False,
                }
                for ini, fim in self._recaida_sem_evento()
            ]
        )
        if not info_mesmo_mtv:
            exigem = criados.filtered(
                lambda r: r.dt_ini_afast >= INICIO_INFO_MESMO_MTV
                and r._codigo_motivo() in MOTIVOS_INFO_MESMO_MTV
                and r._exige_info_mesmo_mtv(r._codigo_motivo())
            )
            if exigem:
                raise UserError(
                    _(
                        "Os afastamentos pendentes vêm até %(rec)s dias depois de "
                        "outro afastamento do mesmo motivo, e o leiaute S-1.3 exige "
                        "informar se é a mesma doença: chame a ação com "
                        "info_mesmo_mtv='S' ou 'N' (ou preencha o campo em cada "
                        "evento)."
                    )
                    % {"rec": DIAS_RECAIDA}
                )
        return criados

    def _validar_afastamento_devido(self, cod_mot):
        """Recusa o S-2230 de doença (motivo 03) que o MOS não manda informar.

        Doença curta é opcional: sem ``informar_opcional`` o evento não é gerado,
        mas nada impede o usuário de pedi-lo. O motivo 01 não tem limite. O
        término acompanha o início já gerado; só sem início avalia o período.
        """
        self.ensure_one()
        if self.informar_opcional:
            return
        inicio, fim = self.dt_ini_afast, self.dt_term_afast
        leave_model = self.env["hr.leave"].sudo()
        dominio = [
            ("employee_id", "=", self.employee_id.id),
            ("state", "=", "validate"),
            ("holiday_status_id.l10n_br_afastamento_inss", "=", True),
        ]
        if inicio:
            if cod_mot != MOTIVO_DOENCA:
                return
            if not fim:
                # Início em aberto: o término vem do afastamento registrado, para
                # não deixar aberto no eSocial um afastamento que acabou curto.
                leave = leave_model.search(
                    dominio + [("request_date_from", "=", inicio)], limit=1
                )
                if not leave:
                    return
                fim = leave.request_date_to
        else:
            leave = leave_model.search(
                dominio + [("request_date_to", "=", fim)], limit=1
            )
            if not leave:
                return
            inicio = leave.request_date_from
            if self.sudo().search_count(
                [
                    ("employee_id", "=", self.employee_id.id),
                    ("dt_ini_afast", "=", inicio),
                    ("id", "!=", self.id),
                ]
            ):
                return
        if not self._periodo_devido(inicio, fim):
            raise UserError(
                _(
                    "Doença não relacionada ao trabalho de %(dias)s dia(s) não é "
                    "de informação obrigatória no S-2230 (acima de %(lim)s dias, "
                    "ou recaída pela mesma doença em até %(rec)s dias; MOS do "
                    "eSocial). Marque 'Informar mesmo sem obrigatoriedade' para "
                    "gerar assim mesmo."
                )
                % {"dias": _dias(inicio, fim), "lim": DIAS_EMPRESA, "rec": DIAS_RECAIDA}
            )

    def _codigo_motivo(self):
        self.ensure_one()
        return self.cod_mot_afast or self.motivo_afastamento_id.codigo

    def _inicio_do_contrato(self, inicio):
        """Início do contrato do empregado vigente em ``inicio`` (ou ``None``)."""
        self.ensure_one()
        contratos = self.employee_id.sudo().contract_ids.filtered(
            lambda c: c.date_start
            and c.date_start <= inicio
            and (not c.date_end or c.date_end >= inicio)
        )
        return max(contratos.mapped("date_start")) if contratos else None

    def _periodos_mesmo_motivo(self, cod_mot, inicio):
        """Períodos ``(inicio, fim)`` do mesmo motivo e contrato, antes de ``inicio``.

        O leiaute conta por contrato e por motivo: acidente (01) e doença (03) não
        são anteriores um do outro. O término vem do próprio S-2230, do S-2230 só
        de término que o segue (fluxo do ``l10n_br_hr_sst_cat``) ou do afastamento
        registrado; só sem nenhum deles o período fica em aberto (``None``). Doença
        sem S-2230 só conta quando é de informação obrigatória: o eSocial não
        conhece a opcional que nunca foi enviada.
        """
        self.ensure_one()
        outros = self.sudo().search(
            [("employee_id", "=", self.employee_id.id), ("id", "!=", self.id)]
        )
        terminos = sorted(
            r.dt_term_afast for r in outros if not r.dt_ini_afast and r.dt_term_afast
        )
        leaves = [
            (lv.request_date_from, lv.request_date_to)
            for lv in self.env["hr.leave"]
            .sudo()
            .search(
                [
                    ("employee_id", "=", self.employee_id.id),
                    ("state", "=", "validate"),
                ]
            )
        ]

        def fim_de(ini, proprio=None):
            if proprio:
                return proprio
            for termino in terminos:
                if termino >= ini:
                    return termino
            for de, ate in leaves:
                # O CAT grava o último dia trabalhado: o afastamento começa no dia
                # seguinte.
                if 0 <= (de - ini).days <= 1:
                    return ate
            return None

        com_inicio = [r for r in outros if r.dt_ini_afast]
        periodos = {}
        for outro in com_inicio:
            if outro._codigo_motivo() == cod_mot:
                ini = outro.dt_ini_afast
                periodos.setdefault(ini, (ini, fim_de(ini, outro.dt_term_afast)))
        if cod_mot == MOTIVO_DOENCA:
            acidentes = [
                r.dt_ini_afast
                for r in com_inicio
                if r._codigo_motivo() == MOTIVO_TRABALHO
            ]
            for ini, fim in self._afastamentos_inss():
                if ini in periodos or any(0 <= (ini - a).days <= 1 for a in acidentes):
                    continue
                if self._periodo_devido(ini, fim):
                    periodos[ini] = (ini, fim)
        contrato = self._inicio_do_contrato(inicio)
        return [
            p
            for p in periodos.values()
            if p[0] < inicio and (not contrato or p[0] >= contrato)
        ]

    def _exige_info_mesmo_mtv(self, cod_mot):
        """Há afastamento do mesmo motivo nos 60 dias antes deste início?"""
        self.ensure_one()
        return any(
            fim is None or (self.dt_ini_afast - fim).days <= DIAS_RECAIDA
            for _ini, fim in self._periodos_mesmo_motivo(cod_mot, self.dt_ini_afast)
        )

    def _info_mesmo_mtv_para_xml(self, cod_mot):
        """Valor do ``infoMesmoMtv`` (S/N) ou ``None`` quando não vai no evento."""
        self.ensure_one()
        if (
            not self.dt_ini_afast
            or self.dt_ini_afast < INICIO_INFO_MESMO_MTV
            or cod_mot not in MOTIVOS_INFO_MESMO_MTV
        ):
            if self.info_mesmo_mtv:
                _logger.warning(
                    "S-2230 %s: infoMesmoMtv descartado (só vale para os motivos "
                    "01 e 03 com início a partir de %s).",
                    self.id,
                    INICIO_INFO_MESMO_MTV,
                )
            return None
        exige = self._exige_info_mesmo_mtv(cod_mot)
        if self.info_mesmo_mtv:
            # Sem anterior o leiaute admite só vazio ou N; S não vai.
            return self.info_mesmo_mtv if exige or self.info_mesmo_mtv == "N" else None
        if exige:
            raise UserError(
                _(
                    "O afastamento de %(ini)s (motivo %(mot)s) vem até %(rec)s dias "
                    "depois de outro afastamento do mesmo motivo: o leiaute S-1.3 "
                    "exige informar se é a mesma doença/acidente. Preencha o campo 'Mesmo "
                    "motivo do afastamento anterior' (info_mesmo_mtv: S ou N) do "
                    "S-2230; se o anterior não foi informado ao eSocial, use N."
                )
                % {
                    "ini": self.dt_ini_afast.strftime("%d/%m/%Y"),
                    "mot": cod_mot,
                    "rec": DIAS_RECAIDA,
                }
            )
        return None

    def _to_esociallib_dict(self):
        self.ensure_one()
        employee = self.employee_id

        cpf = employee.cnpj_cpf
        if not cpf:
            raise UserError(
                _("Empregado '%(name)s' não possui CPF configurado.")
                % {"name": employee.name}
            )
        cpf_limpo = "".join(c for c in cpf if c.isdigit())

        matricula = employee.l10n_br_esocial_matricula

        if not self.dt_ini_afast and not self.dt_term_afast:
            raise UserError(_("Informe a data de início ou término do afastamento."))

        cod_mot = self.cod_mot_afast
        if not cod_mot and self.motivo_afastamento_id:
            cod_mot = self.motivo_afastamento_id.codigo

        if self.dt_ini_afast and not cod_mot:
            raise UserError(
                _(
                    "Código do motivo de afastamento é obrigatório "
                    "ao informar início do afastamento."
                )
            )

        self._validar_afastamento_devido(cod_mot)

        ide = self._get_ide_empregador()
        proc = self._get_proc_info()

        data = {
            "tp_insc": ide["tp_insc"],
            "nr_insc": ide["nr_insc"],
            "proc_emi": proc["proc_emi"],
            "ver_proc": proc["ver_proc"],
            "cpf_trab": cpf_limpo,
        }

        if matricula:
            data["matricula"] = matricula

        if self.dt_ini_afast:
            data["dt_ini_afast"] = str(self.dt_ini_afast)
            data["cod_mot_afast"] = cod_mot
            info_mesmo_mtv = self._info_mesmo_mtv_para_xml(cod_mot)
            if info_mesmo_mtv:
                data["info_mesmo_mtv"] = info_mesmo_mtv

        if self.dt_term_afast:
            data["dt_term_afast"] = str(self.dt_term_afast)

        return data
