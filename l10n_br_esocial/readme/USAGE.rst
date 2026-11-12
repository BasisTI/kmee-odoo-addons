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
#. Para o salário dos dias de licença-maternidade ir ao S-1200 como
   salário-maternidade: marque **Licença-maternidade (eSocial)** no tipo de
   afastamento; crie uma regra com natureza 4050 e incidência INSS 21 (ela só
   define a rubrica no S-1010) e aponte-a em **Rubrica de Salário-Maternidade**
   na regra do salário. O S-1200 divide o valor do holerite entre as duas
   rubricas pelos dias de licença (mês comercial de 30 dias); sem essa
   configuração o salário segue com a natureza 1000 e a geração avisa.
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
   início do contrato; o cargo e o CBO vêm do **Cargo**; a remuneração é o
   salário do contrato (por mês) e o local de trabalho é o **Endereço de
   Trabalho**. **Cadastramento inicial** fica em *Não* (início de TSVE).
#. Estagiário (categorias 901 e 906): no grupo **eSocial - Trabalhador sem
   vínculo e estágio** do contrato, preencha a **Natureza** (sem padrão; 906
   só aceita *Não obrigatório*), o **Nível** (obrigatório na 901), a
   **Instituição de Ensino** (parceiro com CNPJ válido), o **Agente de
   Integração** e o **Supervisor do Estágio** (opcionais), a área de atuação e
   a apólice. O término previsto é a **data final do contrato**, posterior ao
   início.
#. A **Natureza da Atividade** do contrato é obrigatória nas categorias 201,
   202, 401, 731, 734 e 738 e não é enviada nas 721, 722, 771 e 901.
#. As categorias que exigem grupo próprio (dirigente sindical 401, cedido 305 e
   410, mandato eletivo 304) são recusadas: este módulo ainda não gera
   esses grupos.
#. S-2306 (alteração contratual): ``l10n_br.esocial.s2306``, com a **Data da
   Alteração** (não anterior ao início do contrato). Reenvia cargo, remuneração,
   local e, no estágio, as informações do estágio como estão no contrato.
#. S-2399 (término): ``l10n_br.esocial.s2399``, com a **Data do Término** (não
   anterior ao início nem mais de 10 dias à frente). O **Motivo do Término** só
   vale para a categoria 721 (e é obrigatório nela); a **Pensão Alimentícia**
   é obrigatória nas categorias 201, 202 e 721 (término depois de 21/04/2019) e
   não se informa nas demais.
#. Como no S-2200, a geração junta, numa só mensagem, tudo o que falta no
   cadastro, e o XML é conferido contra o XSD do leiaute S-1.3 quando os
   schemas estão na ``esociallib``.
