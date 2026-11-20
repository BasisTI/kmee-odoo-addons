**Saldo de salário na rescisão e holerite mensal do mesmo período**

O SALDO_SALARIO da rescisão desconta o salário que o holerite mensal do mesmo
período já pagou, para que os dias não sejam pagos duas vezes. O vínculo é
mantido num único ponto, a gravação do holerite mensal: toda vez que muda o que
o mensal conta na compensação (estado, linhas, período, contrato ou estrutura;
cancelado não conta), a rescisão do mesmo período é reconciliada, sem recálculo
manual:

* rescisão em rascunho/verificação: é recalculada na mesma transação;
* rescisão já confirmada: a alteração do mensal (calcular, cancelar, excluir,
  reabrir um cancelado, trocar período ou contrato) é recusada com mensagem;
  volte a rescisão para rascunho primeiro. Confirmar um mensal sem mudança do
  que ele paga continua permitido.

**Férias gozadas e holerite mensal do mesmo período**

O holerite mensal paga só os dias fora das férias (CLT arts. 129 e 145): os dias
de gozo do recibo de férias (estrutura FÉRIAS, não cancelado, do mesmo contrato)
que caem no período saem do SALARIO_BASE e dos adicionais proporcionais, no mês
comercial de 30 dias. O período de gozo começa em ``date_from`` do recibo e dura
``Dias de Férias Gozadas`` (limitado a ``date_to``); o abono pecuniário não sai
do salário. Férias que atravessam dois meses descontam em cada mês só os dias
que cabem nele. A rescisão do mesmo período também desconta os dias de férias
no saldo de salário.

O vínculo é mantido no mesmo ponto único da compensação acima: ao lançar,
calcular, alterar (período, dias, contrato, estrutura), cancelar, reabrir ou
excluir um recibo de férias, os holerites mensais e as rescisões sobrepostos em
rascunho/verificação são recalculados na mesma transação; se algum já estiver
confirmado, a alteração do recibo é recusada com mensagem (volte o confirmado
para rascunho primeiro).

**Periculosidade e insalubridade entre mensal e rescisão**

O que o holerite mensal paga de periculosidade e insalubridade conta como
participação do mensal, ao lado do salário, no mesmo ponto único da
compensação acima. Se só o adicional do mensal muda (por exemplo, o indicador
do contrato é marcado entre o cálculo do mensal e o da rescisão), a rescisão
em rascunho/verificação é recalculada na mesma transação; a rescisão
confirmada recusa a alteração (volte-a para rascunho antes). O saldo de
salário compensa o mensal parcela a parcela (salário, salário-maternidade e
cada adicional, arredondados como no mensal), sem resíduo de R$ 0,01.

**Média dos adicionais em férias, 13º e rescisão**

A base segue a letra do CLT art. 142, § 6º (TG-133):

- **Janela:** férias, abono e férias vencidas usam o período aquisitivo da
  alocação; as férias proporcionais da rescisão, o período aquisitivo em curso até
  o desligamento; o 13º (inclusive o da rescisão), o ano civil.
- **Média só se o adicional não foi uniforme.** Se o valor pago em todos os meses
  do período (já atualizado) é o vigente, vale o vigente. Senão vale a média, mesmo
  para quem tem o adicional hoje mas não o teve no período todo: não há mais o
  "maior entre o cheio e a média". Sem mensal confirmado no período, vale o vigente.
- **Divisor:** os dias de salário de cada mês divididos por 30. Mês sem dias de
  salário (férias gozadas o mês inteiro, afastamento) sai do divisor; mês parcial
  entra proporcional aos dias trabalhados.
- **Aviso prévio indenizado** (e os arts. 479 e 480 e o desconto do aviso): a
  remuneração do momento, o adicional vigente, sem média.
- **Reajustes:** cada importância é multiplicada por salário atual / salário do mês
  (periculosidade) ou salário mínimo atual / salário mínimo do mês (insalubridade,
  calculada sobre o mínimo).

Só entram mensais confirmados de competência anterior à do holerite. Não há
histórico do indicador no contrato: vale o valor pago em cada mensal. O saldo de
salário, que paga os dias trabalhados, usa só o adicional vigente.

**Limite:** a média só lê os mensais do contrato atual (mesmo limite da média
habitual, RF-18). Na transferência para um novo contrato, o histórico do contrato
anterior não entra: sem mensal na janela, vale o adicional vigente do contrato novo.

**Migração (18.0.1.12.0):** em bancos instalados, a migração troca a chamada
``tools.br.adicionais_fixos(contract)`` pela da verba (``'ferias'``,
``'ferias_proporcionais'``, ``'13'`` ou ``'momento'``) só nas regras cuja fórmula
gravada é igual à da 1.11.0 (inclusive as férias vencidas). Regra personalizada
fica como está, com aviso no log. A chamada antiga, sem verba, passa a valer o
adicional vigente (sem média): quem mantém a fórmula personalizada precisa
informar a verba na chamada. Holerites já calculados não mudam.

**Causas de rescisão (TG-96)**

O ``Tipo de Rescisão`` define as verbas, a multa do FGTS e o ``mtvDeslig`` do
S-2299 (tabela 19 do eSocial; o S-2299 usa o motivo do tipo e, sem tipo, o do
contrato):

* Justa causa (01): sem aviso, 13º, férias proporcionais nem multa.
* Sem justa causa (02): aviso integral, 13º, férias proporcionais, multa de 40%.
* Término antecipado pelo empregador, art. 479 (03): sem aviso; 13º e férias
  proporcionais; indenização do art. 479; multa de 40%.
* Término antecipado pelo empregado, art. 480 (04): sem aviso nem multa; 13º e
  férias proporcionais; desconto do art. 480.
* Culpa recíproca, art. 484 e Súmula 14 do TST (05): metade do aviso, do 13º e
  das férias proporcionais; multa de 20%.
* Término do contrato a prazo (06): sem aviso nem multa; 13º e férias
  proporcionais.
* Pedido de demissão (07): sem aviso do empregador nem multa; 13º e férias
  proporcionais; desconto do aviso não cumprido, se for o caso.
* Rescisão indireta, art. 483 (17): como a dispensa sem justa causa.
* Força maior, art. 502 (27): sem aviso; 13º e férias proporcionais; multa de
  20%.
* Acordo, art. 484-A (33): metade do aviso; 13º e férias proporcionais; multa
  de 20%.

As férias vencidas são devidas em qualquer causa (CLT art. 146). O aviso só
gera verba quando marcado ``Indenizado``; ``Trabalhado`` já foi pago na folha.

Com aviso ``Indenizado``, o contrato é projetado até o fim do aviso (Súmula 371
do TST; CLT art. 487 § 1º). O período aquisitivo que se completa dentro da
projeção (alocação de Férias que termina até a data projetada) é pago inteiro em
``FERIAS_VENCIDAS`` e ``ADICIONAL_FERIAS_VENCIDAS``, com a média de adicionais
do período dele, e as férias proporcionais contam do aniversário seguinte. Esse
período não é pago em dobro.

A alocação de Férias é a única fonte do período: a rescisão **recusa o cálculo**
se não houver alocação validada do último período aquisitivo completo até a data
projetada (a mensagem traz o empregado, o holerite e as datas do período a
criar; no cálculo em lote, junta todos os recusados). Vale a alocação que
termina no último ano até a data projetada, o que cobre o período
reiniciado no retorno ao serviço (CLT art. 133 § 2º). Crie e valide a
alocação, e calcule de novo. Com a rescisão confirmada, as datas, as faltas, os
dias, o estado (recusar), o empregado, o tipo e o arquivamento da alocação que
ela pagou não podem ser alterados: volte a rescisão para rascunho.

Mesmo com os períodos fora do aniversário de admissão, a alocação do período
anterior não vale pelo que se completa na projeção (só a que termina no último
ano até a data projetada). A rescisão também **recusa** duas alocações de
Férias validadas com períodos que se sobrepõem (pagariam o período mais de uma
vez): a mensagem lista as alocações; recuse ou arquive a duplicada. Períodos
consecutivos, um começando no dia seguinte ao fim do outro, não se sobrepõem.

* **Término antecipado do contrato a prazo:** informe o ``Termo do Contrato a
  Prazo``. Pelo empregador, a rescisão paga a indenização do art. 479 (metade
  da remuneração dos dias até o termo; indenizatória, sem INSS, IRRF nem FGTS).
  Pelo empregado, desconta o ``Prejuízo do Empregador`` informado (art. 480),
  limitado ao valor do art. 479 e a um mês de remuneração (art. 477, §5º);
  em branco, não há desconto.
* **Aviso não cumprido:** no pedido de demissão, ``Aviso Prévio`` = ``Não
  Cumprido pelo Empregado`` desconta 30 dias de salário (art. 487, §2º).

**Multa do FGTS na rescisão**

A multa (40% na dispensa sem justa causa; 20% no acordo do art. 484-A) é
informativa: aparece no TRCT, mas vai à conta vinculada pela guia do FGTS
Digital e **não entra no líquido** (``NET``). A base soma o saldo da conta
vinculada (``Saldo FGTS na Conta Vinculada``, do extrato; sem ele, a estimativa
de 8% do salário por mês completo, sem juros) ao depósito do mês da rescisão: o
FGTS do holerite mensal da mesma competência (mesmo quando a rescisão já o
compensou no saldo de salário), o FGTS do saldo de salário desta rescisão, o
do 13º e o do aviso prévio indenizado. Informe no campo o saldo **para fins rescisórios**, isto é,
o do extrato anterior ao mês da rescisão (sem o depósito do mês, que a regra
soma), para não contá-lo duas vezes. O saldo não pode ser negativo; zero é o
mesmo que em branco e cai na estimativa. O
FGTS do mensal integra a compensação entre holerites: alterá-lo recalcula a
rescisão em rascunho e é recusado se ela já estiver confirmada.

**Aprendiz: FGTS de 2% e INSS nas férias e na rescisão**

O aprendiz (``Tipo de Contrato`` = Aprendiz) recolhe FGTS de 2% (Lei 8.036/90,
art. 15, §7º) sobre as férias, o saldo de salário, o aviso prévio indenizado e o
13º, e o INSS pela tabela comum em todas as verbas tributáveis, inclusive o saldo
de salário e o 13º da rescisão. Só o percentual do FGTS muda; as incidências das
rubricas são as do empregado comum. Em bancos instalados as regras trocam na
atualização do módulo só se estiverem como a versão anterior; regra
personalizada fica como está, com aviso no log.

**FGTS do 13º (1ª e 2ª parcelas)**

A 1ª parcela do 13º não tem INSS nem IRRF, mas gera FGTS (8% do adiantamento) na
competência em que é paga (Lei 8.036/90, art. 15). A 2ª parcela recolhe 8% só
sobre a diferença entre o 13º bruto e a 1ª parcela informada em
``l10n_br_primeira_parcela_13_paga``, de modo que o total do ano é 8% do 13º.
O FGTS é encargo do empregador e não entra no líquido.

Na rescisão, o FGTS do 13º proporcional abate o já recolhido nas 1ªs parcelas
do mesmo ano (holerites de 1ª parcela confirmados e em vigor); se a 1ª parcela
for maior que o FGTS do proporcional, o FGTS do 13º da rescisão é zero. A base
da multa soma o FGTS do 13º da rescisão e o das 1ªs parcelas. O desconto do 13º
já pago no líquido do TRCT não é tratado aqui.

**Abono pecuniário com as médias**

O abono pecuniário (e o seu 1/3) é pago pela mesma remuneração das férias, por
dia vendido (CLT art. 143 §1º): salário, mais a média das verbas variáveis
habituais dos holerites mensais confirmados (Súmula 45 do TST), mais os
adicionais fixos do contrato. Abono e 1/3 do abono não entram na base de INSS
nem de FGTS; o 1/3 do abono segue tributável pelo IRRF (COSIT 209/2021).

**Férias de período aquisitivo vencido**

A alocação de férias vale até o fim do período concessivo, os 12 meses
seguintes ao fim do período aquisitivo (CLT art. 134): o tipo Férias aparece no
seletor do tipo de folga, com o saldo da alocação, e a ausência é aceita sem
criar um segundo saldo sem data final. O saldo e os dias tomados seguem a mesma
regra do padrão do ``hr_holidays``, só com a validade estendida; o total
consumido por alocação não passa dos dias de direito, qualquer que seja a ordem
em que as ausências são lançadas. ``date_to`` da alocação continua sendo o fim
do período aquisitivo (dobra, férias vencidas e recibo o leem).

Depois do concessivo as férias são devidas em dobro (CLT art. 137): o módulo só
aplica a dobra na rescisão (férias vencidas); a ausência, ou a parte dela que
passa do concessivo, não é aceita pelo saldo vencido.

**13º já pago na rescisão (TG-97)**

A rescisão considera o 13º que o contrato já recebeu no ano do desligamento.
Só contam os holerites de 13º (1ª parcela, 2ª parcela e 13º integral)
**confirmados**, em vigor (sem estorno) e do mesmo contrato e ano:

* **1ª parcela (adiantamento)**: o 13º proporcional da rescisão sai inteiro e o
  adiantamento sai como desconto próprio, ``ADIANTAMENTO_13``, como no TRCT. É
  a natureza 9214 da tabela 3 do eSocial, "13º salário - Desconto de
  adiantamento" (a 9200 exclui a 1ª parcela do 13º; a rubrica padrão eSocial5040
  usa a 9214). Vale em toda causa, inclusive na justa causa (sem 13º devido). O
  desconto não deixa o líquido negativo; o que não couber vai à linha
  informativa ``NAO_DESCONTADO_ADIANTAMENTO_13`` (fora do líquido).
* **2ª parcela (ou 13º integral)**: o 13º do ano está quitado e a rescisão paga
  só a diferença dos avos, inclusive os projetados pelo aviso indenizado (2ª
  parcela de 2026 de 2.000,00 e dispensa em 22/12 com aviso até 24/01/2027: 13
  avos, 2.166,67 devidos, 166,67 pagos). Se o quitado passa do devido (justa
  causa ou culpa recíproca depois da 2ª parcela), o 13º da rescisão é zero e o
  excesso é descontado (ver abaixo).
* **Encargos**: o INSS, o IRRF e a pensão do 13º incidem sobre o 13º devido no
  ano (``DECIMO_DEVIDO``, linha informativa) menos o retido na 2ª parcela. O
  FGTS do 13º recolhe só o que falta (8% do devido menos o das duas parcelas) e o
  já recolhido continua na base da multa. A 1ª parcela não retém INSS nem IRRF.

Rescisão em rascunho recalcula sozinha quando a parcela é confirmada, estornada
ou cancelada; rescisão confirmada recusa a mudança (volte-a para rascunho antes).

**13º pago além do devido (TG-141)**

Quando a 2ª parcela (ou o 13º integral) confirmada já pagou mais 13º do que a
rescisão reconhece como devido (justa causa, culpa recíproca, pedido de demissão
antes de 15/12 com a 2ª parcela pagando 12 avos), a rescisão cobra o excesso:

* ``DESCONTO_13_EXCESSO``: desconto do excesso (o 13º quitado menos o devido).
  eSocial: natureza 9214 da tabela 3 com as incidências do 13º (CP 12, IRRF 12 e
  FGTS 12, MOS S-1.3 item 15.3: o desconto de verba paga indevidamente usa a
  natureza e a incidência do pagamento; rubrica padrão eSocial5041). Exemplo:
  salário de 3.000,00, pedido de demissão em 10/12 com a 2ª parcela já paga com
  12 avos: devido de 11 avos, 2.750,00; excesso de 250,00.
* Ordem e limites: o adiantamento do 13º, o aviso não cumprido e o art. 480
  vêm antes; o excesso fica com o que sobrar. O conjunto dos descontos não passa
  de um mês de remuneração (CLT art. 477, §5º) e o líquido não fica negativo. O
  que não couber vai à linha informativa ``NAO_DESCONTADO_13_EXCESSO`` (bruto,
  fora do líquido e do S-2299), acompanhada de ``CREDITO_INSS_13_RESTANTE`` e
  ``CREDITO_IRRF_13_RESTANTE`` (o INSS e o IRRF ainda retidos sobre a parte não
  descontada: imposto sobre o quitado menos o desconto, menos o imposto sobre
  o devido) e de ``A_COBRAR_13_EXCESSO``: o bruto não descontado menos esse
  crédito, que é o valor a cobrar fora da rescisão. Se o empregado pagar, o DP
  retifica o S-2299 incluindo o desconto e as devoluções do restante (MOS
  S-1.3, item 15.2).
* ``DEVOLUCAO_INSS_13`` e ``DEVOLUCAO_IRRF_13``: o INSS e o IRRF do 13º
  retidos na 2ª parcela acima do imposto sobre o 13º devido voltam ao empregado,
  cada um em rubrica própria (tpRubr 1, com a natureza e a incidência do
  desconto que devolvem, MOS S-1.3 item 15.1: INSS 9201, CP 32 e IRRF 42; IRRF
  9203 e IRRF 32). A devolução é exata: o retido menos o imposto sobre o 13º
  que o empregado mantém (o quitado menos o desconto). Se o desconto ficou
  limitado, só volta o imposto da parte descontada; sem desconto, nada volta.
* A pensão retida sobre o excesso **não** volta: foi repassada ao beneficiário
  (TG-141#P1). A base do IRRF do 13º deduz a pensão efetivamente paga no ano e
  nunca fica negativa. Para mudar a regra, ver ``_l10n_br_pensao_13_devolvida``.
* O FGTS do 13º não é recolhido de novo, e o recolhido sobre o excesso continua
  na base da multa.

Mesma integridade entre holerites: a rescisão aberta recalcula quando a 2ª
parcela muda; a confirmada recusa.

13º sobre o aviso prévio indenizado (TG-136)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Na rescisão com aviso indenizado, o 13º sai em duas rubricas:

* ``DECIMO_RESCISAO``: os avos do 13º proporcional, até a data do desligamento (regra
  dos 15 dias, no máximo 12). eSocial natureza 6002; campo 63 do TRCT.
* ``DECIMO_AVISO_INDENIZADO``: os avos que o aviso projeta (Súmula 371 do TST),
  inclusive os do ano seguinte, cada ano com a regra dos 15 dias. eSocial natureza
  6001; campo 70 do TRCT. Só existe quando o aviso acrescenta avos.

INSS, IRRF, pensão e FGTS do 13º seguem calculados sobre o 13º devido total (as duas
rubricas), e o total pago é o mesmo de antes da separação. Exemplo: salário de
2.000,00, admissão em 01/07/2025, dispensa em 13/12/2026 com aviso até 15/01/2027:
11 avos de proporcional (1.833,34) mais 2 do aviso (333,33), 13 avos no total
(2.166,67). Cada rubrica sai pelos próprios avos e o centavo de arredondamento fica no
proporcional. Com a 2ª parcela já paga, ela abate primeiro o proporcional e depois a
rubrica do aviso. O cadastro da natureza de cada rubrica no eSocial é feito na regra
salarial (as naturezas 6001 e 6002 e o campo 70 da rescisória já existem no módulo
``l10n_br_esocial``). Em bancos instalados, a migração 18.0.1.11.0 troca a fórmula do
``DECIMO_RESCISAO`` e o líquido, e liga a rubrica nova à estrutura, só se estiverem
como na 1.10.0; regra personalizada fica como está, com aviso no log. Holerites já
calculados não mudam.

**Férias concedidas depois do período concessivo (em dobro)**

O concessivo (CLT art. 134) deixou de limitar o lançamento: férias de período
aquisitivo vencido podem ser lançadas depois dele. A ausência é aceita e o RH é
avisado, no formulário e numa nota na ausência, com os dias que ficam depois do
fim do concessivo. Esses dias são pagos em dobro, com o terço (CLT art. 137).

No recibo de férias, o campo ``Dias de Férias em Dobro`` conta os dias do gozo
depois do último dia do concessivo (doze meses após o fim do aquisitivo); gozo
que atravessa o fim do concessivo dobra só os dias depois dele (Súmula 81 do
TST). A remuneração de cada dia é a das férias (salário, média e adicionais
fixos): ``FERIAS`` paga todos os dias uma vez e as rubricas ``FERIAS_DOBRO`` e
``ADICIONAL_FERIAS_DOBRO`` (1/3) pagam de novo os dias em dobro. Incidências
da dobra das férias: sem INSS e sem FGTS, com IRRF (eSocial, Tabela 03: natureza 1024, rubrica padrão eSocial1950, ``codIncCP`` 00,
``codIncFGTS`` 00, ``codIncIRRF`` 13; a natureza já inclui o terço).

O abono pecuniário também dobra, com o terço, mas só quando o gozo do recibo
começa depois do fim do concessivo (a data em que as férias foram concedidas);
gozo que começa dentro dele e o atravessa tem abono simples. As rubricas
``ABONO_DOBRO`` e ``ADICIONAL_ABONO_DOBRO`` pagam de novo os dias de abono
(campo ``Dias de Abono em Dobro``). Incidências do abono em dobro: natureza
1024, rubrica padrão eSocial1955 (``codIncCP`` 00, ``codIncFGTS`` 00,
``codIncIRRF`` 75, como o abono simples): indenizatório, fora do GROSS (INSS,
FGTS e pensão percentual) e do IRRF; o terço da dobra do abono não tem rubrica
padrão própria e segue o terço do abono simples (eSocial1940, ``codIncIRRF``
13): tributável pelo IRRF, sem INSS e FGTS.

O período que a ausência debita é decidido em dias corridos, não nos dias úteis
do ``hr_holidays`` (30 dias corridos gastam cerca de 22 e o abono não vira
ausência: a sobra em dias úteis não é saldo de férias). A ausência debita o
período de aquisitivo já completo (CLT art. 134) mais antigo com saldo real
(direito menos as ausências e o abono já lançados): primeiro o vencido, com a
dobra, e só sem vencido com saldo o período ainda dentro do concessivo. Nunca
debita um período cujo aquisitivo ainda não terminou. O aviso de dobra conta só
os dias depois do concessivo do período debitado. Se o concessivo de todos os períodos
completos terminou há mais de cinco anos da data da ausência, a pretensão às
férias está prescrita (CLT art. 149; CF art. 7º, XXIX) e a ausência é recusada
com mensagem clara: os períodos estão prescritos, o sistema não lança
férias desse período e concessão por liberalidade deve ser tratada com o
jurídico (a lei não proíbe o empregador de conceder férias de período
prescrito; a recusa é regra do sistema). O recibo de férias segue a mesma regra:
o período dele só é aceito se o aquisitivo estiver completo no início do gozo e
dentro do horizonte de cinco anos depois do concessivo. A ausência que cruza o
horizonte do período é recusada com a data do horizonte.

Uma ausência debita um único período, sem transbordo. A decisão é uma só (a
análise de ``hr.leave.allocation``): o aviso de dobra, a nota, os dias em dobro
do recibo e a restrição de saldo leem dela, e o recibo de férias que começa no
mesmo dia (rascunho ou confirmado) fixa o período. Para o ``hr_holidays`` todo
período de Férias vale até o fim do concessivo mais cinco anos (o mesmo
deslocamento para todos: a ordem de expiração do ``hr_holidays`` fica igual à
dos períodos e o cálculo de calendário continua curto); quem aceita ou recusa é
a restrição em dias corridos, e o período em aquisição é recusado. Ao recusar, cancelar ou alterar uma ausência, o débito
das seguintes é recalculado: o aviso e uma nota nova refletem o novo período,
e a ausência já lançada que ficar acima do saldo continua lançada, com o
excesso no aviso. Criar, validar, recusar ou excluir uma alocação de Férias e
excluir um recibo em rascunho também reconferem os avisos. A redistribuição pode
levar uma ausência posterior para o período vencido com excesso e dobra, mesmo
com o período seguinte intacto: confira o aviso. O aviso nomeia o período
debitado (datas do aquisitivo) e avisa que um recibo de férias de outro
período, com início no mesmo dia, fixa o débito.

A ORDEM do consumo do ``hr_holidays`` (``leaves_taken`` por período) segue a
expiração, a mesma dos períodos; a QUANTIDADE por período no ``hr_holidays`` é
em dias úteis e pode divergir do débito em dias corridos (a sobra em dias úteis
de um período esgotado em dias corridos pode absorver a ausência seguinte), e
onde um recibo fixa um período mais novo com um vencido ainda aberto o
``hr_holidays`` também diverge. É só exibição: vale o débito do módulo. A
ausência nova que passa do saldo do período é recusada com
mensagem que diz o saldo; lance outra ausência para o resto. A
restrição olha só o período debitado pela ausência criada ou alterada: dado
anterior acima do direito em outro período não bloqueia. Limite: férias
coletivas (CLT art. 140), que atravessam vários períodos de uma vez, ficam fora
desta regra, e a antecipação da Lei 14.437/2022 também. Férias antecipadas
individuais (gozo antes de completo o período aquisitivo) passam a ser recusadas
(CLT art. 134).

O saldo exibido pelo ``hr_holidays`` (formulário da ausência e painel de
saldos) continua em dias úteis e só enxerga o concessivo: ele não reflete o
saldo real em dias corridos nem mostra o período vencido. A regra que vale para
aceitar ou recusar a ausência é a de dias corridos acima; o seletor do tipo
Férias a respeita.

O terço sobre o abono pecuniário pago na vigência do contrato é tributável pelo
IRRF: Solução de Consulta COSIT nº 209, de 16/12/2021 (DOU de 29/12/2021), cuja
ementa diz que o abono do art. 143 da CLT tem a tributação afastada pela
jurisprudência do STJ reconhecida pelo Ato Declaratório PGFN nº 6/2006, e que o
adicional constitucional incidente sobre o abono, pago no curso do contrato, é
tributado. O ADI RFB nº 28/2009 não consta dessa consulta. A página oficial
(normas.receita.fazenda.gov.br) não abriu na verificação; o texto da ementa foi
conferido numa republicação do ato.

Um período aquisitivo com recibo de férias confirmado não aceita mudar as datas
nem as faltas (que mudam os dias de direito): volte o recibo para rascunho; o
recibo em rascunho recalcula ao ser calculado de novo. O recibo impresso mostra
os dias em dobro no cabeçalho.

Multa do FGTS na rescisão: o saldo informado é o extrato do FGTS Digital
posicionado antes do mês da rescisão. A base soma a ele o depósito do mês da
rescisão e o do mês anterior (Lei 8.036/90, art. 18, § 1º; Decreto 99.684/90,
art. 9º, § 1º), os recibos de férias, rateados por dias de gozo em cada mês (a
mesma função que decide a competência de cada parte no S-1200 de
``l10n_br_esocial``, MOS S-1.3, S-1010, item 23, pp. 112-114): entra a parte do FGTS do recibo cujo mês é o
mês anterior ou o da rescisão (gozo de 20/10 a 18/11, rescisão em dezembro: só a
parte de novembro), e o FGTS do 13º pago em um desses dois meses (em janeiro, o
de dezembro do ano anterior): o que já venceu antes está no extrato. Sem saldo informado,
entra o recibo que se sobrepõe ao período da rescisão. Extrato posicionado depois do dia 20 do mês
da rescisão já traz o mês anterior e a base o soma de novo. Holerite de qualquer
um desses meses calculado ou alterado depois recalcula a rescisão aberta e é
recusado se a rescisão estiver confirmada. Holerite confirmado não
recalcula (``compute_sheet`` recusa) e a edição direta de uma linha de holerite
que outro confirmado usa é recusada como a do formulário. Se a regra ``NET`` ou
``MULTA_FGTS`` da rescisão foi personalizada e ficou defasada, o holerite mostra
um aviso no topo e registra uma nota no histórico.
