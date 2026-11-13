Ciclo de uma competência:

#. Cadastre o estabelecimento (S-1005) e as lotações (S-1020) e transmita-os.
#. Gere o S-1200 dos holerites confirmados.
#. Informe a **Data de Pagamento** nos holerites pagos e use a ação **Gerar
   S-1210** (o evento é por regime de caixa).
#. Aguarde o aceite de todos os eventos periódicos: o fechamento é bloqueado
   enquanto houver evento da competência sem aceite.
#. Gere o S-1299. Para corrigir uma competência fechada, transmita antes a
   reabertura (S-1298).
#. Evento aceito por engano é desfeito com o S-3000.

Ambiente de transmissão (trava de produção):

#. O ambiente padrão da empresa é **2 - Produção Restrita**.
#. O ambiente **1 - Produção** fica bloqueado: a empresa não o aceita e o lote
   não transmite nem consulta com ele. Para liberar de propósito, um
   administrador define o parâmetro de sistema
   ``l10n_br_esocial.permitir_producao`` como ``True``.
#. Antes de transmitir e de consultar, o lote confere o ambiente da empresa e o
   ``tpAmb`` do XML de cada evento; se divergirem, gere o evento de novo.

Rubricas (S-1010 e S-1200):

#. Regra sem **Incidência IRRF** sai no S-1010 com o código 09 (verba que não é
   rendimento, retenção, isenção nem dedução de IRRF); o 00 expirou em 30/06/2021.
   Regra antiga que ainda guarda um código expirado mostra um aviso na aba
   eSocial e o S-1010 recusa a geração até a incidência ser trocada. Para listar
   as regras nessa situação, filtre por ``l10n_br_esocial_cod_inc_irrf_expirado``
   (campo calculado, pesquisável).

#. Regra de **vencimento** (tipo de rubrica 1) sem **Incidência IRRF** não gera o
   S-1010: o 09 tiraria o rendimento da base de IRRF e o governo aceitaria o
   evento sem aviso. A geração é recusada, com a lista das regras, até a escolha
   explícita: 11 a 14 (tributável), 70 a 79 ou 700 a 704 (isento) ou 09. Desconto
   e informativa continuam saindo com o 09. As regras padrão do
   ``l10n_br_hr_payroll`` não trazem dados eSocial; preencha a incidência ao
   configurar cada rubrica.

#. O **Código Rubrica eSocial** identifica a rubrica. Regras de estruturas
   diferentes (mensal, férias, 13º, rescisão) podem repetir o código desde que
   tenham a mesma natureza, o mesmo tipo e as mesmas incidências; com definição
   diferente, o Odoo recusa.
#. Gere o S-1010 uma vez por rubrica, não por regra: um segundo S-1010 do mesmo
   código, empresa e início de validade é recusado. O método
   ``l10n_br.esocial.s1010.criar_para_regras`` cria um S-1010 por rubrica a
   partir de um conjunto de regras.
#. Salário-maternidade tem natureza própria (4050 mensal, 4051 13º). A
   incidência INSS 21, 22, 25 ou 26 com a natureza 1000 é recusada.
#. O salário-maternidade tem rubrica própria no holerite (regra
   ``SALARIO_MATERNIDADE`` do ``l10n_br_hr_payroll``), que o eSocial já traz
   configurada com natureza 4050 e incidências INSS 21, IRRF 11 e FGTS 11. Marque
   **Licença-maternidade** no tipo de afastamento; o S-1200 leva a rubrica pelo
   valor do holerite, sem divisão por dias. Defina o **Código Rubrica eSocial**
   (padrão ``SAL_MATERNIDADE``) se a sua tabela usar outro. A configuração antiga
   (**Licença-maternidade (eSocial)** e **Rubrica de Salário-Maternidade**) foi
   substituída por esta; as regras que tinham o vínculo aparecem no log da
   atualização. A rubrica usa a tabela de rubricas que a empresa já tem e, onde
   há S-1010, ganha o dela (gere e transmita-o antes do primeiro S-1200). Holerite
   calculado antes da atualização, com dias de licença e sem a rubrica, é
   recusado na geração do S-1200: volte-o para rascunho, recalcule e confirme.
   A regra criada à mão com o mecanismo antigo deve ser desativada.
#. Regra de provento ou desconto com valor no holerite e sem código ou natureza
   eSocial fica fora do S-1200; a geração registra um aviso no log e no campo
   **Avisos da geração** do S-1200.

Tabelas de incidência (S-1010):

#. As listas de **Incidência INSS**, **IRRF** e **FGTS** da regra salarial seguem o
   leiaute S-1.3 (NT 07/2026 rev. 20/10/2026). No IRRF só aparecem os códigos
   vigentes da Tabela 21.
#. Ao atualizar o módulo, regras com um código que saiu do leiaute (por exemplo,
   IRRF ``00``) não são alteradas: o log do servidor avisa quais são, para revisão
   antes de gerar o S-1010.
#. Quando sair outra Nota Técnica, atualize ``tests/leiaute_s13.py`` e os dados do
   módulo juntos; ``test_tabelas_incidencia`` acusa qualquer diferença.

Admissão (S-2200):

#. O S-2200 não usa mais valores fixos: raça/cor, grau de instrução, nascimento,
   sexo, CNPJ do sindicato, jornada, local de trabalho e dependentes vêm do
   cadastro, e a geração recusa o evento (``UserError``) quando algum falta.
#. No **empregado**: **Gênero** (masculino ou feminino), **Data de Nascimento**,
   **Raça/Cor** (``ethnicity``, códigos 1 a 5; o 6 - não informado - é proibido
   no S-2200) e, na aba **Informações Privadas**, grupo **eSocial**, o **Grau de
   Instrução eSocial** (tabela do leiaute S-1.3).
#. No **contrato**: **Sindicato** (parceiro com CNPJ válido), o calendário de
   **Jornada de Trabalho** e, no grupo **eSocial - Jornada**, o **Tipo de
   Jornada** (sem padrão) e o **Tempo Parcial**. As horas semanais (sem os intervalos), o horário
   noturno (22h às 5h) e a descrição da jornada saem do calendário.
#. O **local de trabalho** é o **Endereço de Trabalho** do empregado: precisa ser
   um estabelecimento do empregador (CNPJ com a mesma raiz da empresa) e estar
   no S-1005.
#. **Dependentes**: nos parentes do empregado, preencha o **Tipo de Dependente
   eSocial** (Tabela 07) para declará-lo. Parente sem tipo não é enviado; se ele
   estiver marcado para IRRF, salário-família ou incapacidade, a geração é
   recusada. O CPF é obrigatório para dependente de IRRF, o tipo 99 exige a
   descrição, o nascimento não pode estar no futuro e tipos encerrados na
   Tabela 07 são recusados. Se os **Dependentes IRRF** ou os **Filhos para
   Salário-Família** da folha divergirem dos declarados, o campo **Avisos da
   geração** do S-2200 registra a diferença.
#. A geração junta, numa só mensagem, tudo o que falta no cadastro.
#. O **Tempo Parcial** é conferido com a categoria (1 só para a 104; 2 e 3 não
   valem para a 104) e, para admissões a partir de 23/11/2026, com as horas
   (25, 30 e 26 h) e com a jornada 12 x 36 (exige 0).

Trabalhador sem vínculo - estagiário e demais categorias (S-2300, S-2306, S-2399):

#. A **categoria** do trabalhador decide o evento: empregados e agentes públicos
   com vínculo (101 a 111, 301, 302, 303, 306, 307, 309, 310, 312, 314) usam
   S-2200/S-2206/S-2299; as categorias sem vínculo (201, 202, 304, 305, 308,
   311, 313, 401, 410, 501, 701 a 781, 901 a 904 e 906) usam
   S-2300/S-2306/S-2399. O S-2200, o S-2206 e o S-2299 recusam categoria sem
   vínculo, e o S-2300, o S-2306 e o S-2399 recusam categoria com vínculo.
#. S-2300 (início): gere pelo modelo ``l10n_br.esocial.s2300``, com o
   trabalhador e o contrato. Os dados pessoais (sexo, raça/cor, grau de
   instrução, nascimento, dependentes) saem do cadastro como no S-2200; o
   **País de Nascimento** e a **Nacionalidade** do empregado precisam ter o
   código do Bacen (o eSocial usa os 3 primeiros dígitos). O início é a data de
   início do contrato; o cargo e o CBO vêm do **Cargo** (opcionais nas
   categorias 901, 903, 904 e 906: sem CBO o grupo não vai); a remuneração é o
   salário do contrato (por mês; obrigatória nas 721, 722, 771 e 906); o local
   de trabalho é o **Endereço de Trabalho** e só vai nas categorias que o
   leiaute lista (201, 202, 721, 722, 723, 731, 734, 738, 761, 771, 901, 902 e
   906; antes de 22/01/2024 é facultativo). A categoria 721 exige a **Data de
   Opção pelo FGTS** do contrato.
#. **Cadastramento inicial** fica em *Não* (início de TSVE). Com *Sim*, informe
   na empresa (aba eSocial) o **Início dos Eventos Não Periódicos**: o início do
   contrato deve ser anterior a ela (e, com *Não*, igual ou posterior).
#. Estagiário (categorias 901 e 906): no grupo **eSocial - Trabalhador sem
   vínculo e estágio** do contrato, preencha a **Natureza** (sem padrão; 906
   só aceita *Não obrigatório*), o **Nível** (obrigatório na 901), a
   **Instituição de Ensino** (parceiro com CNPJ válido), o **Agente de
   Integração** e o **Supervisor do Estágio** (opcionais e só na 901), a área
   de atuação e a apólice. O término previsto é a **data final do contrato**, posterior ao
   início.
#. A **Natureza da Atividade** do contrato é obrigatória nas categorias 201,
   202, 401, 731, 734 e 738 e não é enviada nas 721, 722, 771 e 901.
#. As categorias que exigem grupo próprio (dirigente sindical 401, cedido 305 e
   410, mandato eletivo 304) são recusadas: este módulo ainda não gera
   esses grupos.
#. S-2306 (alteração contratual): ``l10n_br.esocial.s2306``, com a **Data da
   Alteração** (não anterior ao início do contrato nem mais de 180 dias à
   frente). O trabalhador é identificado só por CPF e matrícula. Reenvia cargo, remuneração,
   local e, no estágio, as informações do estágio como estão no contrato.
#. S-2399 (término): ``l10n_br.esocial.s2399``, com a **Data do Término** (não
   anterior ao início nem mais de 10 dias à frente). O **Motivo do Término** só
   vale para a categoria 721 (e é obrigatório nela); a **Pensão Alimentícia**
   é obrigatória nas categorias 201, 202 e 721 com término depois de
   21/04/2019 (opcional até essa data) e não se informa nas demais. Como no
   S-2306, o trabalhador é identificado só por CPF e matrícula.
#. Como no S-2200, a geração junta, numa só mensagem, tudo o que falta no
   cadastro, e o XML é conferido contra o XSD do leiaute S-1.3 quando os
   schemas estão na ``esociallib``.

Afastamento por doença (S-2230, MOS S-1.3 itens 3.1, 4.1 e 5):

#. **Acidente/doença do trabalho (motivo 01)**: informado desde o 1º dia,
   qualquer que seja a duração. O Odoo não aplica limite.
#. **Doença não relacionada ao trabalho (motivo 03)**: obrigatória acima de 15
   dias, na recaída pela mesma doença em até 60 dias (soma acima de 15 dias,
   com a janela contada do término do primeiro afastamento) e em até 60 dias do
   retorno de um afastamento acima de 15 dias. Na recaída, cada afastamento da
   cadeia vai no seu evento, com a própria data de início.
#. Doença curta fora de recaída é **opcional**: o Odoo não gera o evento, e a
   recusa informa isso. Marque **Informar mesmo sem obrigatoriedade** para
   gerar assim mesmo. O término de um início já gerado vai sempre.
#. Quando o evento atual fecha uma recaída, os afastamentos anteriores da
   cadeia que ainda não têm S-2230 não são gerados sozinhos (o prazo do MOS é
   de envio individual, em atraso): use a ação
   ``action_gerar_recaida_pendente`` do evento para criá-los.
#. O critério usa os afastamentos validados de tipo **Afastamento
   Previdenciário** (``l10n_br_afastamento_inss``) do empregado. Acidente do
   trabalho (S-2230 de motivo 01 no mesmo início) não soma com doença comum.
   Os demais motivos (maternidade, férias, licença remunerada etc.) não têm o
   limite de 15 dias.
#. **Mesmo motivo do afastamento anterior** (``infoMesmoMtv``, leiaute S-1.3,
   início a partir de 26/10/2026, só motivos 01 e 03): quando há outro
   afastamento do mesmo motivo do empregado nos 60 dias anteriores ao início, o
   evento informa **S** (mesma doença/acidente) ou **N**. O afastamento do Odoo
   não tem CID, então o usuário preenche o campo **Mesmo motivo do afastamento
   anterior** (``info_mesmo_mtv``) no S-2230; vazio, o evento é recusado com
   mensagem clara. Sem anterior na janela, o campo não é exigido (``S`` não vai,
   só ``N``), e fora dos motivos 01/03 ou antes da data de vigência ele não vai
   no XML (com aviso no log). O anterior conta por contrato e por motivo
   (acidente e doença não são anteriores um do outro); o término dele vem do
   próprio S-2230, do S-2230 só de término que o segue ou do afastamento
   registrado. Doença anterior sem S-2230 só conta quando era de informação
   obrigatória. Se o anterior não foi informado ao eSocial, use ``N``. A ação
   ``action_gerar_recaida_pendente`` recebe ``info_mesmo_mtv`` e recusa sem ele
   quando algum pendente exige o campo.

Pagamentos e informe de rendimentos (S-1210, leiaute S-1.3 - evtPgtos):

O ``infoIRComplem`` (que substitui a DIRF) só sai quando algum holerite pago
tem desconto com incidência de IRRF que o leiaute manda detalhar. A
``tpPgto`` vale 1 = S-1200, 2 = S-2299, 3 = S-2399, 4 = S-1202, 5 = S-1207.

#. **Dependentes** (``dedDepen``): os parentes com tipo eSocial e **Dependente
   para IRRF** (mesmos do S-2200) recebem a dedução por dependente vigente na
   competência. O número de dependentes de IRRF da folha precisa ser igual ao
   declarado; se diferir, o evento é recusado.
#. **Pensão alimentícia** (``penAlim``): rubrica de desconto com incidência
   IRRF 51 a 54. Marque **Beneficiário da Pensão Alimentícia** em um (e só
   um) parente, com CPF. Se ele não tem tipo de dependente eSocial, é
   declarado em ``infoDep`` (o leiaute pede ``infoDep`` só para quem o S-2200
   não cadastrou).
#. **Plano de saúde** (``planSaude``): rubrica de desconto com incidência IRRF
   67 ou 9067 (ou natureza 9219). Informe no contrato o **CNPJ da operadora**
   e o registro na ANS; o **Plano de Saúde - Valor Mensal** de cada
   dependente sai do desconto do holerite, e o que sobra é o titular.
#. **Previdência complementar** (``previdCompl``): rubrica de desconto com
   incidência IRRF 46-48 (privada), 61, 62 e 66 (FAPI) ou 63-65 (Funpresp).
   Informe o **CNPJ da entidade** no contrato.
#. Falta de CPF, CNPJ, beneficiário ou valor recusa o evento com a lista do
   que falta; nada é preenchido por padrão. Reembolso médico (``infoReembMed``)
   e moléstia grave (``dtLaudo``) não são gerados.

Desligamento (S-2299): ``indPagtoAPI`` (aviso prévio indenizado) existe no
S-2299, não no S-1210. Informe o **Holerite de Rescisão**: com o módulo de
rescisão, o indicativo é ``S`` só quando a folha apurou a verba de aviso
indenizado (sem justa causa ou acordo), e ``dtProjFimAPI`` é o desligamento mais
os dias de aviso (Lei 12.506/2011). Sem o holerite vale o que foi digitado, e
``S`` exige a data projetada, igual ou posterior ao desligamento.
Com o holerite de rescisão **confirmado** e em vigor, o S-2299 declara as
verbas em ``verbasResc``, um ``dmDev`` por holerite (``ideDmDev`` ``RES`` + id do
holerite, nunca igual ao do S-1200) e uma ``detVerbas`` por linha com valor e
com código e natureza de rubrica eSocial na regra: aviso indenizado, férias
indenizadas e terço, 13º rescisório, saldo de salário e descontos. ``indApurIR``
(0, apuração normal) e ``infoAgNocivo`` saem conforme o leiaute S-1.3;
``grauExp`` é 1 (não ensejador), ou o grau do adicional de aposentadoria
especial do contrato quando o módulo de SST está instalado. Linha com valor e
sem código ou natureza de rubrica, ou de sinal contrário ao da rubrica (provento
negativo, desconto positivo), fica fora e é listada em **Avisos da geração** (na
tela do evento e no log): nada com valor some em silêncio. A multa do FGTS
(``MULTA_FGTS``) vai à conta vinculada e não é verba paga ao trabalhador, por
isso não entra no ``verbasResc``. Rescisão que não está confirmada, e os
``mtvDeslig`` para os quais o leiaute proíbe o grupo (11, 12, 13, 25, 28, 29,
30, 34, 36, 43 e 44), não geram ``verbasResc``. ``dtAvPrv`` (data da concessão
do aviso) não é gerada: a rescisão não a registra. O S-2299 de uma rescisão não
se gera duas vezes: para regerar, exclua o anterior por S-3000.

O leiaute recusa o S-1200 da competência do desligamento rescisório
(``REGRA_REMUN_JA_EXISTE_DESLIGAMENTO``); por isso o S-2299 com ``verbasResc``
declara também os holerites confirmados do mês do desligamento (mensal e
férias; o 13º tem competência própria) e o S-1200 não é gerado para eles. Se
algum já tem S-1200 vigente, o S-2299 recusa e pede o S-3000 dele antes. O
pagamento desses holerites vai no S-1210 com ``tpPgto`` 2, ``perRef`` do mês do
desligamento e o ``ideDmDev`` do S-2299, depois do aceite do S-2299.

No S-1200, o ``indApurIR`` sai em cada rubrica (obrigatório desde 07/2021) e o
``infoAgNocivo`` para categorias do RGPS; regras de provento indenizatório
(``PROV_INDENIZ``) e tributável só pelo IRRF sem rubrica também geram aviso.

Holerite estornado: o estorno (Devolução) e o holerite que ele desfez ficam
fora de vigor e não vão ao eSocial: a geração do S-1200, do S-1210 e do S-2299
e a conferência da competência (holerites e totalizadores) os ignoram e usam o
holerite novo. O holerite estornado que já tem S-1200, S-1210 ou S-2299 gerado
mostra o aviso **eSocial a retificar** (filtro e menu *Holerites a retificar*).

Fluxo (MOS S-1.3, cap. I item 15.2 e S-1200 item 31):

#. Se há **S-1210 transmitido** referenciando o S-1200 do estornado, exclua-o
   antes por S-3000 (o eSocial só aceita o retificador depois); a geração do
   S-1200 retificador recusa até lá.
#. Gere o S-1200 do holerite novo: sai o **retificador** (``indRetif`` = 2) com
   o recibo do evento aceito do estornado, levando também os holerites que
   continuam em vigor naquele evento. Quando o retificador é aceito (ou forçado
   como sucesso), o evento anterior passa a **Retificado**.
#. Reenvie o S-1210 (selecione de novo os holerites pagos): sai como original.

Se o evento do estornado ainda não foi aceito (sem recibo), a geração espera o
retorno do lote. Evento em rascunho/validado do estornado volta a rascunho, sai
do lote e não pode ser validado. Competência fechada (S-1299 sem S-1298 depois)
recusa a geração. Estorno sem holerite novo, ou S-2299 de rescisão estornada
(o módulo não gera retificador de S-2299): exclua o evento por S-3000.
