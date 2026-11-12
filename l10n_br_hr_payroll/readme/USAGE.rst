**Proporcionalidade do salário**

O ``SALARIO_BASE`` e o adicional de periculosidade saem proporcionais aos dias de
salário do mês (mês comercial de 30 dias):

* admissão no mês: dias corridos até o fim do mês (teto de 30);
* desligamento no mês: dias corridos até a data final do contrato;
* afastamento previdenciário: marque *Afastamento Previdenciário* no tipo de
  ausência. A empresa paga os 15 primeiros dias e os seguintes, aprovados, saem do
  salário (são pagos pelo INSS).

**Periculosidade e insalubridade nas bases**

Os dois adicionais entram no bruto (``GROSS``) e, por ele, nas bases do INSS, do
FGTS e do IRRF. Em férias, abono pecuniário, 13º (adiantamento, bruto e o da
rescisão), aviso prévio indenizado, férias indenizadas e vencidas e saldo de
salário (``l10n_br_hr_vacation``), o adicional entra na base pelo valor cheio do
contrato (30% do salário; 10, 20 ou 40% do salário mínimo), não por média: é um
percentual constante, e não uma parcela variável (CLT art. 142, § 5º; Súmulas 132
e 139 do TST). No saldo de salário o adicional acompanha os dias de salário e
desconta o que o holerite mensal do mesmo período já pagou.

**Desconto de DSR por falta**

A falta injustificada faz perder o repouso da semana em que ocorreu (Lei 605/49,
art. 6º). O ``DESC_DSR`` é o salário diário (salário / 30) vezes o número de
semanas com falta; duas faltas na mesma semana descontam um repouso só. A semana
vai de segunda a domingo.

* Informe os dias na aba de faltas do holerite (*Dias de falta*); o total de
  *Faltas Injustificadas* continua descontando o salário.
* Falta sem data (só a contagem) conta numa semana própria.
* Dia dentro de férias gozadas ou de afastamento previdenciário não gera falta.
* Semana que atravessa a virada do mês é descontada uma vez só, no holerite que
  traz a primeira falta dela.
* Falta justificada não entra na contagem.

**Estrutura mensal e médias**

As médias de férias, 13º e rescisão (e o salário já pago, que a rescisão não paga
de novo) leem os holerites das estruturas *mensais*. Mensal é a estrutura que tem
a rubrica ``SALARIO_BASE`` (categoria BASIC) e nenhuma rubrica de férias, 13º ou
rescisão (``FERIAS``, ``ADIANTAMENTO_13``, ``DECIMO_TERCEIRO_BRUTO``,
``SALDO_SALARIO``). Vale pelas rubricas, não pelo código: uma estrutura própria
(como a ``CLT_BASIS``) entra sem cadastro.

**Reflexo no DSR de horas extras e adicional noturno**

As horas extras e o adicional noturno do mês refletem no repouso semanal
remunerado (Lei 605/49, art. 7º, a; Súmulas 172 e 60 do TST). As rubricas
``DSR_HE`` e ``DSR_NOTURNO`` são o valor da verba ÷ dias úteis × dias de repouso
do mês, entram no bruto (logo nas bases de INSS, IRRF e FGTS) e na média habitual
que compõe férias, 13º e rescisão.

* Repouso é domingo ou feriado; dia útil é o restante (segunda a sábado).
* O módulo não tem calendário de feriados próprio: cadastre-os como *ausência
  global* (Tempo livre ▸ Configuração ▸ Feriados) no calendário de trabalho do
  contrato, ou sem calendário para valerem a todos. Sem feriado cadastrado, só os
  domingos são repouso e o reflexo sai menor que o devido.
* É feriado o dia cujo expediente a ausência global cobre por inteiro, lido no
  fuso do calendário do contrato (sem calendário: o da empresa), não no de quem
  lançou. Ausência que termina à meia-noite não toca o dia seguinte, meio
  expediente não é feriado, e a ausência que cobre dois ou mais dias por inteiro
  (recesso coletivo) fica de fora; para dois feriados seguidos, lance um registro
  por dia. Sem calendário, lance de 00:00 a 23:59:59 do fuso do calendário.
* Em banco existente a atualização liga as rubricas à estrutura CLT. Há uma só
  rubrica ``DSR_HE``, a da folha; com o ``l10n_br_hr_payroll_attendance``
  instalado, os dias do reflexo são os mesmos com ou sem apuração (domingos e
  feriados do calendário da folha), e a apuração só acrescenta os feriados que
  marcou nos dias que cobre.

Salário-maternidade
~~~~~~~~~~~~~~~~~~~

Marque **Licença-maternidade** no tipo de afastamento. Os dias de licença
aprovada saem do ``SALARIO_BASE`` e vão para a rubrica ``SALARIO_MATERNIDADE``
(salário × dias ÷ 30), no mesmo conjunto de dias do salário: admissão,
desligamento, afastamento do INSS e férias já pagas são descontados antes, e a
soma das duas rubricas fecha com o salário dos dias. Em período maior que 30 dias
(anual, 13º) a licença entra na proporção dos dias do período.

* A rubrica está no bruto: entra nas bases de INSS, IRRF e FGTS.
* ``COMP_SALARIO_MATERNIDADE`` (informativa, categoria INFO) é o valor a
  compensar na guia previdenciária (Lei 8.213/91, art. 72, § 1º); não entra no
  líquido nem nas bases.
* CPP e RAT: o parâmetro **CPP e RAT sobre o salário-maternidade**, na aba
  *Encargos da Folha* da empresa, vem desmarcado: o
  salário-maternidade sai dessas duas bases (STF, Tema 72); as contribuições a
  terceiros seguem incidindo. Marcado, ele entra nas duas (comportamento
  anterior). Em banco existente, a atualização desmarca só a empresa que ainda
  não tem holerite com ``SALARIO_MATERNIDADE``; a que já tem fica como está. A
  escolha é do DP/contabilidade.
* O salário-maternidade é o salário contratual dos dias de licença; adicionais e
  médias de verbas variáveis continuam nas suas próprias rubricas.
* Em banco existente a atualização troca as fórmulas padrão de ``SALARIO_BASE``,
  ``CPP`` e ``RAT`` (as personalizadas ficam como estão) e liga as rubricas novas
  à estrutura CLT.

Limites do salário-maternidade:

* Só vale onde a rubrica está na estrutura: a CLT e a Estatutário a trazem. Em
  estrutura própria com ``SALARIO_BASE`` e sem ``SALARIO_MATERNIDADE`` o salário
  dos dias de licença segue inteiro no ``SALARIO_BASE`` (nada é descontado);
  ligue a rubrica para pagá-lo na própria.
* ``SALARIO_BASE`` personalizada: a atualização não liga a rubrica nova (pagaria o
  salário em dobro) e avisa no log. Adapte a fórmula ao desconto dos dias de
  licença (ver a fórmula padrão) e ligue a rubrica à estrutura.
* Não há parcela de 13º de salário-maternidade (natureza 4051) nem a compensação
  dela: o 13º segue o cálculo anterior.
* Rescisão sem holerite mensal no mês paga os dias de licença no
  ``SALDO_SALARIO``, como salário comum.
* Férias sobrepostas à licença prevalecem: os dias de gozo já foram pagos no
  recibo e não viram salário-maternidade.
* ``COMP_SALARIO_MATERNIDADE`` é informativa: nenhuma guia do repositório a lê e
  ela não gera lançamento contábil (o ``l10n_br_hr_payroll_account`` debita a
  ``SALARIO_MATERNIDADE`` em despesa de salários, como o ``SALARIO_BASE``). A
  dedução na guia é feita pelo usuário ou pelo sistema que gera a guia, a partir
  do total desta rubrica.

Estorno de holerite confirmado
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

*Devolução* (``refund_sheet``) cria um holerite de estorno (``credit_note``) já
confirmado, com as mesmas linhas do original, e grava nele o vínculo em
*Holerite estornado*. O par (estorno e estornado) fica "fora de vigor"
(``l10n_br_fora_de_vigor``): não conta para período duplicado, DSR, médias de
férias/13º/rescisão, salário já pago na rescisão nem para a integridade entre
holerites. O período aceita então um holerite novo, calculado do zero.

* Com o ``l10n_br_hr_payroll_account``, o estorno lança o inverso do lançamento
  do original.
* Estornar muda a participação do original: holerites dependentes (DSR da
  semana, férias, rescisão) em rascunho são recalculados; confirmado recusa o
  estorno até voltar a rascunho, como em qualquer outra alteração.
* Cancelar o estorno devolve a vigência ao original.
* Os eventos do eSocial já gerados (S-1200 e semelhantes) **não** são
  retificados pelo estorno: isso fica para o usuário.
