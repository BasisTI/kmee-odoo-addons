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
#. Regra de provento ou desconto com valor no holerite e sem código ou natureza
   eSocial fica fora do S-1200; a geração registra um aviso no log e no campo
   **Avisos da geração** do S-1200.
