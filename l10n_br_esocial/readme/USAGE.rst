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
   **Raça/Cor** (``ethnicity``, códigos 1 a 6) e, na aba eSocial, **Grau de
   Instrução eSocial** (tabela do leiaute S-1.3).
#. No **contrato**: **Sindicato** (parceiro com CNPJ válido), o calendário de
   **Jornada de Trabalho** e, no grupo **eSocial - Jornada**, o **Tipo de
   Jornada** (sem padrão) e o **Tempo Parcial**. As horas semanais, o horário
   noturno (22h às 5h) e a descrição da jornada saem do calendário.
#. O **local de trabalho** é o **Endereço de Trabalho** do empregado: precisa ser
   um estabelecimento do empregador (CNPJ com a mesma raiz da empresa) e estar
   no S-1005.
#. **Dependentes**: nos parentes do empregado, preencha o **Tipo de Dependente
   eSocial** (Tabela 07) para declará-lo. Parente sem tipo não é enviado. O CPF é
   obrigatório para dependente de IRRF, e o tipo 99 exige a descrição.
