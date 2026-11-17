# Copyright 2024 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import logging

from dateutil.relativedelta import relativedelta
from lxml import etree

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from .s1200_remuneracao import CATEGORIAS_DECLARAVEIS, CODIGOS_FORA_DAS_VERBAS

# Situações do evento que contam como declarado (ver ``hr_payslip.py``).
EVENTO_VIGENTE = ("draft", "validated", "pending", "sent", "success")
# mtvDeslig com ``verbasResc`` proibido (grupo N no leiaute S-1.3).
MOTIVOS_SEM_VERBAS_RESC = frozenset("11 12 13 25 28 29 30 34 36 43 44".split())

# Prefixo do ``ideDmDev`` que o S-2299 dá a cada holerite (``RES`` + id).
PREFIXO_IDE_DM_DEV = "RES"

_logger = logging.getLogger(__name__)


class ESocialS2299(models.Model):
    _name = "l10n_br.esocial.s2299"
    _inherit = "l10n_br.esocial.base.intermediario"
    _description = "eSocial S-2299 - Desligamento"

    employee_id = fields.Many2one(
        "hr.employee",
        string="Empregado",
        required=True,
        ondelete="cascade",
    )
    contract_id = fields.Many2one(
        "hr.contract",
        string="Contrato",
        required=True,
        ondelete="cascade",
    )
    dt_deslig = fields.Date(
        string="Data do Desligamento",
        required=True,
    )
    motivo_desligamento_id = fields.Many2one(
        "l10n_br.esocial.motivo.desligamento",
        string="Motivo Desligamento",
        required=True,
    )
    payslip_id = fields.Many2one(
        "hr.payslip",
        string="Holerite de Rescisão",
        ondelete="set null",
        help="Holerite da rescisão. Com o módulo de rescisão instalado, o "
        "aviso prévio (indenizado ou não) e a data projetada do seu término "
        "saem daqui e prevalecem sobre os campos abaixo.",
    )
    ind_pagto_api = fields.Selection(
        [
            ("S", "Sim"),
            ("N", "Não"),
        ],
        string="Aviso Prévio Indenizado",
        default="N",
        help="indPagtoAPI: o empregador pagou aviso prévio indenizado ao "
        "empregado. Só é 'Sim' quando há a verba de aviso indenizado (dispensa "
        "sem justa causa ou acordo, com aviso marcado como indenizado); aviso "
        "trabalhado, pedido de demissão e justa causa são 'Não'.",
    )
    dt_proj_fim_api = fields.Date(
        string="Data Projetada Fim Aviso Prévio",
        help="dtProjFimAPI: obrigatória com aviso indenizado, igual ou "
        "posterior à data do desligamento.",
    )

    ind_retif = fields.Selection(
        [("1", "Original"), ("2", "Retificação")],
        string="Indicativo Retificação",
        default="1",
        required=True,
        copy=False,
    )
    nr_recibo = fields.Char(
        string="Nº Recibo Retificado",
        copy=False,
        help="Recibo do S-2299 aceito que este retificador substitui. "
        "Obrigatório quando o Indicativo de Retificação for 'Retificação'.",
    )
    evento_retificado_id = fields.Many2one(
        "l10n_br.esocial.evento",
        string="Evento Retificado",
        readonly=True,
        copy=False,
        help="S-2299 aceito que este retificador substitui. Quando o retificador "
        "é aceito, o evento retificado passa a 'Retificado'.",
    )

    @api.constrains("nr_recibo")
    def _check_nr_recibo(self):
        for rec in self:
            rec._validar_nr_recibo(rec.nr_recibo, _("Nº Recibo"))

    def _prepare_evento_vals(self, xml, id_evento):
        vals = super()._prepare_evento_vals(xml, id_evento)
        vals.update(
            {
                "ind_retif": self.ind_retif,
                "operacao": "R" if self.ind_retif == "2" else "I",
                "evento_retificado_id": self.evento_retificado_id.id,
            }
        )
        return vals

    def _aviso_indenizado(self):
        """``(indPagtoAPI, dtProjFimAPI)`` do desligamento.

        Com o holerite de rescisão, vale a regra da folha
        (``_l10n_br_aviso_indenizado_devido``) e a data projetada é o
        desligamento mais os dias de aviso (Lei 12.506/2011); sem ele, vale o
        que foi informado no evento.
        """
        self.ensure_one()
        slip = self.payslip_id
        if slip and hasattr(slip, "_l10n_br_aviso_indenizado_devido"):
            if slip._l10n_br_aviso_indenizado_devido():
                dias = slip._l10n_br_dias_aviso_previo()
                return "S", self.dt_deslig + relativedelta(days=dias)
            return "N", False
        return self.ind_pagto_api or "N", self.dt_proj_fim_api

    def _pens_alim(self):
        """``pensAlim``: sempre 0 (sem retenção de FGTS para pensão alimentícia).

        Leiaute S-1.3, ``evtDeslig.xsd``, infoDeslig/pensAlim, e MOS S-1.3
        (S-2299, item 5, p. 281-282): o grupo informa a retenção da pensão
        sobre o **saldo do FGTS**, obrigatório e exclusivo para o celetista
        (``tpRegTrab`` = 1 no S-2200, que o módulo declara para todo vínculo).
        A pensão que a folha desconta do empregado
        (``l10n_br_pensao_percentual``/``l10n_br_pensao_alimenticia``) é sobre a
        remuneração, outra base, e não entra aqui. Enquanto o cadastro não tiver
        um campo próprio de retenção sobre o saldo do FGTS, a declaração é 0, o
        mesmo que o TRCT deixa em branco no campo 29 (decisão TG-137#P1).
        """
        self.ensure_one()
        return {"pens_alim": 0}

    def _data_aviso_previo(self):
        """``dtAvPrv``: data de concessão do aviso prévio, quando a folha a tem.

        Opcional no leiaute; se informada, igual ou posterior à admissão e
        igual ou anterior a ``dtDeslig``. Vem da rescisão (módulo de rescisão).
        """
        self.ensure_one()
        slip = self.payslip_id
        data = getattr(slip, "l10n_br_data_aviso_previo", False) if slip else False
        if not data:
            return False
        admissao = self.contract_id.date_start
        if data > self.dt_deslig or (admissao and data < admissao):
            raise UserError(
                _(
                    "S-2299 de '%(name)s': a data de concessão do aviso prévio "
                    "(%(aviso)s) deve estar entre a admissão (%(adm)s) e o "
                    "desligamento (%(deslig)s)."
                )
                % {
                    "name": self.employee_id.name,
                    "aviso": data,
                    "adm": admissao,
                    "deslig": self.dt_deslig,
                }
            )
        return data

    avisos = fields.Text(
        string="Avisos da geração",
        readonly=True,
        copy=False,
        help="Linhas da rescisão com valor que ficaram fora das verbas "
        "rescisórias do S-2299: regra sem código ou natureza de rubrica "
        "eSocial, ou provento com valor negativo.",
    )

    def get_ide_dm_dev(self, slip):
        """Identificador do demonstrativo (ideDmDev) de um holerite no S-2299.

        Um por holerite, derivado do id dele: único no trabalhador e na
        competência e nunca igual ao do S-1200 (``DEM`` + id do S-1200). O
        S-1210 de ``tpPgto`` 2 aponta para este identificador.
        """
        return "%s%08d" % (PREFIXO_IDE_DM_DEV, slip.id)

    def _slips_declarados(self):
        """Holerites que o XML deste S-2299 de fato declara em ``verbasResc``.

        Lido do evento gerado (os ``ideDmDev``), não recalculado: o que o
        S-2299 declarou é o que o governo conhece. Recalcular dá outra
        resposta quando a rescisão mudou de estado depois da geração (em
        ``verify`` ao gerar e confirmada depois, estornada depois do aceite) ou
        quando nenhuma rubrica estava configurada, e o S-1210 passaria a
        apontar para um demonstrativo que não existe no XML.
        """
        self.ensure_one()
        vazio = self.env["hr.payslip"]
        xml = self.evento_id.xml_envio
        if not xml:
            return vazio
        try:
            raiz = etree.fromstring(xml.encode("utf-8"))
        except etree.XMLSyntaxError:
            return vazio
        ids = set()
        for el in raiz.iter("{*}ideDmDev"):
            ide = (el.text or "").strip()
            numero = ide[len(PREFIXO_IDE_DM_DEV) :]
            if ide.startswith(PREFIXO_IDE_DM_DEV) and numero.isdigit():
                ids.add(int(numero))
        return vazio.browse(sorted(ids)).exists()

    def _verbas_resc_permitidas(self):
        """O grupo ``verbasResc`` é proibido para alguns ``mtvDeslig`` (leiaute)."""
        return self.motivo_desligamento_id.codigo not in MOTIVOS_SEM_VERBAS_RESC

    def _slips_verbas(self):
        """Holerites cujas verbas o S-2299 declara em ``verbasResc``.

        O leiaute recusa o S-1200 da competência do desligamento rescisório
        (``REGRA_REMUN_JA_EXISTE_DESLIGAMENTO``): a remuneração do mês do
        desligamento (mensal, férias e a própria rescisão) vai no S-2299. O
        13º tem competência própria e segue no S-1200. Só entram holerites
        confirmados e em vigor; com a rescisão em outro estado, nada.
        """
        self.ensure_one()
        vazio = self.env["hr.payslip"]
        rescisao = self.payslip_id
        if (
            not rescisao
            or rescisao.state != "done"
            or rescisao.l10n_br_fora_de_vigor
            or not self._verbas_resc_permitidas()
        ):
            return vazio
        inicio = self.dt_deslig.replace(day=1)
        fim = inicio + relativedelta(months=1, days=-1)
        outros = self.env["hr.payslip"].search(
            [
                ("employee_id", "=", self.employee_id.id),
                ("company_id", "=", self.company_id.id),
                ("state", "=", "done"),
                ("date_from", ">=", inicio),
                ("date_from", "<=", fim),
                ("id", "!=", rescisao.id),
            ]
        )
        outros = outros.filtered(
            lambda slip: not slip.l10n_br_fora_de_vigor
            and not (slip.struct_id.code or "").startswith("13_")
            and slip.struct_id.code != "RESCISAO"
        )
        return rescisao | outros | self._slips_ferias_do_mes_vindas_de_antes()

    def _slips_ferias_do_mes_vindas_de_antes(self):
        """Recibos de férias que começam antes do mês do desligamento e o atravessam.

        O S-1200 deles de ``per_apur`` = mês do desligamento (TG-152: férias que
        atravessam o mês têm um S-1200 por competência) é o que o leiaute recusa
        junto com o S-2299; a parte desse mês vai em ``verbasResc``. ``date_from``
        fica fora do mês, então a busca por ``date_from`` não os acha.
        """
        self.ensure_one()
        mes = self.dt_deslig.strftime("%Y-%m")
        inicio = self.dt_deslig.replace(day=1)
        recibos = self.env["hr.payslip"].search(
            [
                ("employee_id", "=", self.employee_id.id),
                ("company_id", "=", self.company_id.id),
                ("state", "=", "done"),
                ("date_from", "<", inicio),
                ("date_to", ">=", inicio),
            ]
        )
        return recibos.filtered(
            lambda slip: not slip.l10n_br_fora_de_vigor
            and slip.struct_id.code == "FERIAS"
            and mes in [per for per, _dias in slip._l10n_br_competencias_ferias()]
        )

    def _exigir_sem_s1200_vigente(self, slips):
        """Holerite com S-1200 vigente não pode ser declarado de novo aqui."""
        # Só o S-1200 da competência do desligamento conflita: o recibo de férias
        # que atravessa o mês tem os de outras competências, que seguem vigentes.
        mes = self.dt_deslig.strftime("%Y-%m")
        s1200_do_mes = slips.l10n_br_esocial_s1200_ids.filtered(
            lambda s1200: s1200.per_apur == mes and s1200.ind_apuracao == "1"
        )
        eventos = s1200_do_mes.evento_id.filtered(
            lambda evento: evento.state in EVENTO_VIGENTE
        )
        com_s1200 = slips.filtered(
            lambda slip: slip.l10n_br_esocial_s1200_ids.evento_id & eventos
        )
        if com_s1200:
            raise UserError(
                _(
                    "O S-2299 de '%(name)s' declara a remuneração do mês do "
                    "desligamento, mas estes holerites já têm S-1200 vigente: "
                    "%(lista)s. O leiaute recusa o S-1200 da competência do "
                    "desligamento rescisório; desfaça esses S-1200 antes de "
                    "gerar o S-2299: %(como)s."
                )
                % {
                    "name": self.employee_id.name,
                    "lista": ", ".join(slip.number or slip.name for slip in com_s1200),
                    "como": eventos._orientacao_desfazer(),
                }
            )

    def _itens_verbas(self, slip, sem_config):
        """``detVerbas`` do holerite; o que não puder declarar vai a ``sem_config``."""
        itens = []
        mes = self.dt_deslig.strftime("%Y-%m")
        exige_ir = mes >= "2021-07"
        # Recibo de férias que atravessa o mês do desligamento: só a parte desta
        # competência (rateio por dias de gozo), com o 1015/9221 dela.
        parcial = (
            slip.struct_id.code == "FERIAS"
            and len(slip._l10n_br_competencias_ferias()) > 1
        )
        for line in slip.line_ids:
            rule = line.salary_rule_id
            if not line.total or rule.code in CODIGOS_FORA_DAS_VERBAS:
                continue
            if (
                not rule.l10n_br_esocial_nat_rubr_id
                or not rule.l10n_br_esocial_cod_rubr
            ):
                if rule.category_id.code in CATEGORIAS_DECLARAVEIS:
                    sem_config.append(
                        _(
                            "Regra '%(regra)s' (%(code)s) com valor %(valor).2f "
                            "na rescisão e sem código ou natureza de rubrica "
                            "eSocial: fora do S-2299."
                        )
                        % {
                            "regra": rule.name,
                            "code": rule.code,
                            "valor": abs(line.total),
                        }
                    )
                continue
            # vrRubr não tem sinal. O desconto (tpRubr 2) já é a dedução pelo
            # tipo da rubrica e a folha o grava com qualquer sinal (o INSS da
            # rescisão é positivo), então vale o módulo. Provento negativo, que
            # seria declarado como positivo, não se troca em silêncio.
            tp_rubr = rule.l10n_br_esocial_tp_rubr
            if tp_rubr == "1" and line.total < 0:
                sem_config.append(
                    _(
                        "Regra '%(regra)s' (%(code)s) com valor negativo "
                        "%(valor).2f em rubrica de provento (tpRubr 1): fora do "
                        "S-2299; ajuste a rescisão."
                    )
                    % {
                        "regra": rule.name,
                        "code": rule.code,
                        "valor": line.total,
                    }
                )
                continue
            valor = (
                slip._esocial_valor_na_competencia(line, mes) if parcial else line.total
            )
            if not valor:
                continue
            if parcial:
                # Competência do gozo após o pagamento: rubrica "mês do gozo".
                rule = slip._esocial_regra_da_linha(line, mes)
            item = {
                "cod_rubr": rule.l10n_br_esocial_cod_rubr,
                "ide_tab_rubr": rule._esocial_ide_tab_rubr_da_regra(self.company_id),
                "vr_rubr": str(abs(valor)),
            }
            if exige_ir:
                # 0 = apuração normal, sob a folha declarada no eSocial.
                item["ind_apur_ir"] = 0
            itens.append(item)
        if parcial:
            for xmlid, valor in slip._esocial_adiantamentos_ferias(mes):
                regra = self.env.ref(xmlid)
                if "abono" in xmlid:
                    self.env["hr.salary.rule"]._esocial_garantir_par_abono()
                item = {
                    "cod_rubr": regra.l10n_br_esocial_cod_rubr,
                    "ide_tab_rubr": regra._esocial_ide_tab_rubr_da_regra(
                        self.company_id
                    ),
                    "vr_rubr": str(valor),
                }
                if exige_ir:
                    item["ind_apur_ir"] = 0
                itens.append(item)
        return itens

    def _build_verbas_resc(self):
        """``verbasResc``: um ``dmDev`` por holerite do mês do desligamento.

        Entram as linhas com valor, código e natureza de rubrica eSocial: a
        verba de aviso indenizado, as férias indenizadas e o terço, o 13º
        rescisório, o saldo de salário e os descontos. A multa do FGTS não é
        verba paga ao trabalhador (vai à conta vinculada) e fica de fora. Linha
        com valor e sem configuração, ou com sinal contrário, vai a ``avisos``.
        """
        self.ensure_one()
        slips = self._slips_verbas()
        if not slips:
            self.avisos = False
            return []
        self._exigir_sem_s1200_vigente(slips)
        sem_config = []
        company = self.company_id
        cnpj_estab = "".join(c for c in (company.partner_id.vat or "") if c.isdigit())
        demonstrativos = []
        for slip in slips:
            itens = self._itens_verbas(slip, sem_config)
            if not itens:
                continue
            demonstrativos.append(
                {
                    "ide_dm_dev": self.get_ide_dm_dev(slip),
                    "info_per_apur": {
                        "ide_estab_lot": [
                            {
                                "tp_insc": 1,
                                "nr_insc": cnpj_estab,
                                "cod_lotacao": company.l10n_br_esocial_cod_lotacao
                                or "1",
                                "det_verbas": itens,
                            }
                        ],
                    },
                }
            )
        self.avisos = "\n".join(sem_config) if sem_config else False
        if sem_config:
            _logger.warning("eSocial S-2299 %s: %s", self.id, self.avisos)
        return demonstrativos

    def _gerar_xml(self):
        xml = super()._gerar_xml()
        categoria = self.employee_id.l10n_br_esocial_categoria_id.codigo
        if "verbasResc" not in xml or not self._categoria_rgps(categoria):
            return xml
        inicio = self.dt_deslig.replace(day=1)
        fim = inicio + relativedelta(months=1, days=-1)
        grau = self._grau_exp(self.contract_id, inicio, fim)
        return self._xml_com_info_ag_nocivo(xml, "S-2299", "ideEstabLot", grau)

    def _get_event_type(self):
        return "S-2299"

    def _esocial_slips(self):
        return self.payslip_id

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
        if not matricula:
            raise UserError(
                _("Empregado '%(name)s' não possui Matrícula eSocial.")
                % {"name": employee.name}
            )

        categoria = employee.l10n_br_esocial_categoria_id
        if categoria:
            self._validar_categoria_evento(employee, categoria, "S-2299")

        ide = self._get_ide_empregador()
        proc = self._get_proc_info()

        ind_pagto_api, dt_proj_fim_api = self._aviso_indenizado()
        if ind_pagto_api == "S":
            if not dt_proj_fim_api:
                raise UserError(
                    _(
                        "S-2299 de '%(name)s': com aviso prévio indenizado "
                        "(indPagtoAPI = S) informe a Data Projetada Fim Aviso "
                        "Prévio."
                    )
                    % {"name": employee.name}
                )
            if dt_proj_fim_api < self.dt_deslig:
                raise UserError(
                    _(
                        "S-2299 de '%(name)s': a data projetada do fim do aviso "
                        "(%(proj)s) não pode ser anterior ao desligamento "
                        "(%(deslig)s)."
                    )
                    % {
                        "name": employee.name,
                        "proj": dt_proj_fim_api,
                        "deslig": self.dt_deslig,
                    }
                )

        data = {
            "tp_insc": ide["tp_insc"],
            "nr_insc": ide["nr_insc"],
            "proc_emi": proc["proc_emi"],
            "ver_proc": proc["ver_proc"],
            "cpf_trab": cpf_limpo,
            "matricula": matricula,
            "mtv_deslig": self.motivo_desligamento_id.codigo,
            "dt_deslig": str(self.dt_deslig),
            "ind_pagto_api": ind_pagto_api,
        }

        if ind_pagto_api == "S":
            data["dt_proj_fim_api"] = str(dt_proj_fim_api)

        if self.ind_retif == "2":
            if not self.nr_recibo:
                raise UserError(
                    _(
                        "Retificação (ind_retif=2) exige o Nº do Recibo do S-2299 "
                        "aceito a ser retificado."
                    )
                )
            data["ind_retif"] = 2
            data["nr_recibo"] = self.nr_recibo

        data.update(self._pens_alim())
        dt_av_prv = self._data_aviso_previo()
        if dt_av_prv:
            data["dt_av_prv"] = str(dt_av_prv)

        verbas_resc = self._build_verbas_resc()
        if verbas_resc:
            data["verbas_resc"] = verbas_resc

        return data
