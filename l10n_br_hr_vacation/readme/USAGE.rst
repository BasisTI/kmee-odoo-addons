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

A base de férias, 13º, aviso prévio e verbas rescisórias leva o MAIOR entre o
adicional mensal cheio vigente no contrato e a média do que foi pago nos
holerites mensais confirmados dos últimos 12 meses (CLT art. 142, § 6º): quem
tem o adicional hoje recebe o valor cheio; quem o perdeu depois de meses
pagos recebe a média, e não zero. Não há histórico do indicador no contrato:
vale o valor pago em cada mensal confirmado (mês de salário parcial entra pelo
valor proporcional pago, como nas demais médias). O saldo de salário, que paga
os dias trabalhados, usa só o adicional vigente.

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
  causa ou culpa recíproca depois da 2ª parcela), o 13º da rescisão é zero e
  nada é cobrado de volta.
* **Encargos**: o INSS e o IRRF do 13º incidem sobre o total do ano (o da 2ª
  parcela mais o da rescisão) menos o retido na 2ª parcela. O FGTS do 13º
  recolhe só o que falta (8% do total menos o das duas parcelas) e o já
  recolhido continua na base da multa. A 1ª parcela não retém INSS nem IRRF.

Rescisão em rascunho recalcula sozinha quando a parcela é confirmada, estornada
ou cancelada; rescisão confirmada recusa a mudança (volte-a para rascunho antes).
