**Proporcionalidade do salário**

O ``SALARIO_BASE`` e o adicional de periculosidade saem proporcionais aos dias de
salário do mês (mês comercial de 30 dias):

* admissão no mês: dias corridos até o fim do mês (teto de 30);
* desligamento no mês: dias corridos até a data final do contrato;
* afastamento previdenciário: marque *Afastamento Previdenciário* no tipo de
  ausência. A empresa paga os 15 primeiros dias e os seguintes, aprovados, saem do
  salário (são pagos pelo INSS).

**Aprendiz: INSS pela tabela, FGTS de 2%**

O aprendiz (``Tipo de Contrato`` = Aprendiz, categoria 103 do eSocial) tem o INSS
descontado pela tabela progressiva comum, a mesma do empregado CLT, e o FGTS de 2%
(Lei 8.036/90, art. 15, §7º). O 2% é só do FGTS: o INSS patronal, o RAT e os
terceiros do aprendiz não mudam. A regra ``INSS Aprendiz`` (2% da base) foi
desativada e a regra ``INSS`` vale para todos; em bancos instalados a migração
da 18.0.1.13.0 troca as duas só se estiverem como a versão anterior. Regra de INSS
personalizada fica como está, com aviso no log, e o aprendiz segue com ela (sem INSS
em dobro). Holerites já calculados não mudam; o em rascunho recalcula.

**Periculosidade e insalubridade nas bases**

Os dois adicionais entram no bruto (``GROSS``) e, por ele, nas bases do INSS, do
FGTS e do IRRF. Em férias, abono pecuniário, 13º (adiantamento, bruto e o da
rescisão), aviso prévio indenizado, férias indenizadas e vencidas e saldo de
salário (``l10n_br_hr_vacation``), o adicional entra na base pelo valor cheio do
contrato (30% do salário; 10, 20 ou 40% do salário mínimo), não por média: é um
percentual constante, e não uma parcela variável (CLT art. 142, § 5º; Súmulas 132
e 139 do TST). No saldo de salário o adicional acompanha os dias de salário e
desconta o que o holerite mensal do mesmo período já pagou.

**DSR sobre toda hora extra**

O ``DSR_HE`` reflete o valor de TODA regra da categoria *Horas Extras* (``HE``,
filha de *Provento*), qualquer que seja o percentual (Súmula 172 do TST): além de
``HE_50`` e ``HE_100``, uma regra própria de hora extra de CCT (60%, 70%, 75%) entra
no reflexo só por estar nessa categoria, sem mexer na fórmula. A categoria é filha de
Provento, então o valor segue entrando no bruto e nas bases. Em bancos instalados a
migração da 18.0.1.14.0 move ``HE_50`` e ``HE_100`` para a categoria e troca o
``DSR_HE`` só se ele estiver como na versão anterior; regra personalizada fica como
está, com aviso no log. O ``DSR_HE`` tem sequência 7 e só soma o que já foi calculado:
uma regra de hora extra com sequência **maior que 7** fica fora do reflexo, sem aviso;
dê a ela sequência menor que 7.

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
* Falta descoberta depois do fechamento do mês em que ocorreu: lance-a no
  holerite do mês seguinte com a data real e a marca *Competência anterior*. O
  salário do dia é descontado no holerite atual (pela contagem de faltas), mas o
  repouso só se desconta se a semana ainda não foi descontada por falta de
  outro holerite. Falta sem data nunca ocupa uma semana que outro holerite já
  descontou.
* Criar um recibo de férias, validar, recusar ou alterar um afastamento
  previdenciário muda quais faltas valem: os holerites do empregado que mudam
  de desconto de DSR em rascunho são recalculados na hora; se algum já está
  confirmado, a ação é recusada até voltá-lo para rascunho.

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
* O holerite de estorno **não pode ser cancelado** (mesmo com o cancelamento de
  holerites liberado em *Folha de pagamento*): quem errou o estorno calcula um
  holerite novo no período, que agora aceita.
* Os eventos do eSocial já gerados (S-1200 e semelhantes) **não** são
  retificados pelo estorno: isso fica para o usuário.

**RAT e FAP por estabelecimento**

O RAT e o FAP da empresa são o valor padrão. Quando matriz e filiais têm FAP
diferente (o FAP é publicado todo ano, por CNPJ), cadastre uma linha por
estabelecimento em *Folha > Tabelas fiscais > RAT/FAP por Estabelecimento* (ou na
aba *Encargos da Folha* da empresa): CNPJ, início e fim da vigência (mês cheio),
RAT e FAP. A regra RAT usa a linha vigente na competência do holerite para o CNPJ
do **Endereço de Trabalho** do empregado, o mesmo local de trabalho que o S-2200
declara. Sem linha para o estabelecimento na competência, vale o RAT/FAP da
empresa.

A tabela é só fonte do cálculo da folha: o S-1005 **não** a copia. O evento só leva
``aliqRat``/``fap`` (grupo ``aliqGilrat``) quando o usuário os informa no próprio
S-1005, o que o leiaute S-1.3 reserva a processo judicial do FAP
(``procAdmJudFap``), estabelecimento fora da tabela FAP e CNO sem ``cnpjResp``.

Limite: o estabelecimento vem do Endereço de Trabalho *atual* do empregado e o
módulo não guarda histórico de endereço. Ao transferir um empregado de filial,
recalcular um holerite de competência anterior usa o RAT/FAP da filial nova, não
o da filial onde ele estava na época; holerites confirmados não mudam.

**Hora noturna reduzida e percentual do noturno no contrato**

A marca "Usar Hora Noturna Reduzida" do holerite em rascunho segue o contrato,
inclusive ao trocar o contrato do holerite (no formulário e na gravação
direta); holerite confirmado guarda o que valeu. O gerente de contratos sem
acesso à folha pode alterar a marca do contrato. O "Percentual do Adicional
Noturno" aceita valores maiores que 0 e até 100. Só a regra salarial padrão do
adicional noturno lê esse percentual: regra personalizada usa a própria fórmula
e o ignora.

**Pensão alimentícia sobre o FGTS**

Na aba *Folha de Pagamento* do empregado, o grupo *Pensão sobre o FGTS* guarda a
retenção sobre o saldo do FGTS fixada por decisão judicial própria: percentual,
valor fixo (um, outro ou ambos) e a origem (vara e processo). É outra base que a
pensão da folha e não entra no cálculo da rescisão. O S-2299 declara ``pensAlim``
0 (sem dado), 1 (percentual), 2 (valor) ou 3 (ambos) com ``percAliment`` e
``vrAlim``, e o TRCT mostra o campo 29.

**Horista (repouso semanal remunerado)**

A unidade do salário vem de um campo só, a *Unidade do Salário* (``salary_unit``)
do ``l10n_br_hr_contract``, e o código dela é o ``undSalFixo`` do eSocial.
*Hourly* (código 1) faz do contrato um horista: o **Valor da Hora** é o dado do
horista (no eSocial, ``undSalFixo`` 1 com ``vrSalFx`` igual ao valor da hora).
O *Salário* do contrato continua mensal: no horista é o **mensal de
referência** (valor da hora × horas do mês da jornada do contrato, por exemplo
220), calculado e só leitura. Vale-transporte, periculosidade, VA/VR e as
demais regras que leem o Salário usam esse mensal de referência (não as horas
pagas do mês).

Só *Hourly* (1), *Monthly* (5) e o contrato sem unidade (bancos antigos,
calculado como mensal) são suportados. *Daily* (2), *Weekly* (3), *Biweekly*
(4), *Task* (6) e *Não aplicável* (7) são recusados com uma mensagem, no
holerite e na geração do S-2200, do S-2206 e dos eventos de trabalhador sem vínculo (``undSalFixo``): o
mês seria pago em silêncio, e o eSocial exigiria ``dscSalVar`` (6 e 7) e
``vrSalFx`` zero (7). A mensagem lista os contratos e os funcionários a
corrigir. Como a recusa está no cálculo do holerite, **um contrato assim
recusa o lote inteiro** e também as operações em cascata que recalculam
holerites abertos (mudar a convenção coletiva ou um benefício, por exemplo,
quando há holerite aberto de um contrato com unidade não suportada). No
contrato horista, o Valor da Hora é obrigatório; o contrato Hourly de um banco
antigo, sem valor da hora, mantém o Salário gravado (a migração avisa no log
quais são) e o holerite dele é recusado até informar o valor.

Limite: o parâmetro ``payroll.prevent_compute_on_confirm`` não reavalia a
unidade na confirmação; um holerite calculado antes da troca da unidade para
uma não suportada é confirmado sem recusa (só o recálculo recusa).

No holerite, as *Horas Pagas (Horista)* são as horas normais trabalhadas no
mês (vazio: as horas trabalhadas do período, tipo WORK100, menos a jornada
diária de cada falta injustificada); as horas extras continuam em campo
próprio. O salário é horas × valor da hora e a regra ``DSR_HORISTA`` paga o
repouso: horas ÷ dias úteis × (domingos e feriados) × valor da hora (Lei
605/49, art. 7º, b), com os mesmos feriados do ``DSR_HE`` e o mês inteiro como
período (admissão no meio do mês também, como no ``DSR_HE``). O reflexo de
hora extra e de adicional noturno segue em ``DSR_HE`` e ``DSR_NOTURNO``. A
falta com data perde o repouso de um dia por semana (``DESC_DSR``); o horista
não tem ``FALTAS``, porque a falta já tirou as horas pagas. Férias, 13º (1ª parcela, 2ª parcela e integral) e rescisão do horista são
calculados sobre o **salário de referência do horista**, não sobre o mensal de
referência: a média mensal das horas pagas nos holerites mensais confirmados da
janela (período aquisitivo nas férias, ano civil no 13º, 12 meses no aviso
prévio e nos arts. 479 e 480) mais o repouso (``DSR_HORISTA``), pelo **valor da
hora vigente** (CLT, art. 142, § 1º; Lei 4.090/62 e Decreto 57.155/65, art.
2º). Cada mês entra pelas horas pagas, é atualizado do valor da hora daquele
mês para o vigente (o reajuste no período vale para todos) e pesa **dias de
salário ÷ 30**, como a média dos adicionais fixos: a média é a soma ÷ a soma dos
pesos, então férias, admissão ou afastamento no meio do mês não puxam a média.
Mês sem dia de salário (férias ou afastamento o mês todo) fica de fora; mês com
dia e sem hora entra com zero. Janela sem mensal confirmado (por exemplo,
rescisão pouco depois do aniversário do aquisitivo) usa os 12 meses anteriores ao
recibo. Sem nenhum mensal confirmado, valem as horas do **mensal do mesmo contrato
e da mesma competência** do recibo, levadas a 30 dias (horas × 30 ÷ dias de
salário do mensal), pelo valor da hora vigente, mais o repouso; sem esse mensal,
o mensal de referência. O recibo de férias, de 13º ou de rescisão nunca é a fonte
das horas. Limite: na competência da admissão o mensal tem menos dias, e é a
normalização a 30 dias que evita subestimar a base. Limite: contrato que passou
de Monthly a Hourly no meio da janela tem os mensais da fase mensalista lidos
pelas horas do calendário e sem repouso. O TRCT imprime a referência usada nas
verbas. Isso evita pagar a mais, com o divisor da jornada (como 220), quem
tem jornada menor e é desligado nos primeiros meses. A média das horas extras e
do adicional noturno (``media_habitual``) segue como antes. No saldo de salário
da rescisão, o horista recebe as horas do holerite de rescisão × valor da hora
mais o repouso, menos o salário e o repouso que o mensal do período já pagou. A
rubrica do S-2299 é a mesma das demais verbas. Mensalista: nada muda. Holerite
aberto recalcula com o valor da hora vigente; confirmado não muda. Banco já
instalado: a migração 18.0.1.20.0 do ``l10n_br_hr_vacation`` troca as fórmulas
não personalizadas. Fórmula personalizada continua com o mensal de referência
(WARNING no log): use ``tools.br.salario_referencia(contract, verba)`` no lugar
de ``contract.wage``. O contrato que sai de Hourly zera o Valor da Hora, para
que ele não volte a valer quando o contrato retornar a Hourly (informe o valor
de novo); o Salário digitado em contrato Hourly sem Valor da Hora é gravado, não
descartado. A migração 18.0.1.15.0 (e a 18.0.1.17.0) avisa os contratos com
unidade 2, 3, 4, 6 e 7.

**Contagem dos dias de salário (admissão e desligamento).** Na empresa, aba
*Encargos da Folha*, o campo *Contagem dos dias de salário* escolhe como contar
os dias do mês em que o contrato não cobre o mês inteiro. *Dias corridos*
(padrão, o comportamento anterior): os dias do calendário de vigência, com teto
de 30. *Mês comercial*: todo mês tem 30 dias; admitido no dia 14, 30 − 14 + 1 =
17 dias (corridos: 18 num mês de 31 dias); no desligamento, o dia do
desligamento (o último dia do mês vale 30); admissão no dia 31 paga 1 dia. O mês
inteiro paga 30 nos dois modos. O modo vale para o salário, a periculosidade, a
insalubridade, o salário-maternidade, o afastamento previdenciário e as férias
gozadas no mês, e só para período dentro de um mês civil (13º e anual seguem
como antes). O holerite aberto recalcula com o modo atual; o confirmado não
muda. Defina o modo antes de confirmar a folha e não o troque depois: a média dos
adicionais fixos da rescisão (``_l10n_br_media_adicionais_art142``) relê os dias
dos holerites mensais pelo modo vigente, e o saldo de salário compensa o mensal
já pago (zera pelo ``max(…, 0)`` se o modo trocar depois de confirmar o mensal). A regra
do mês comercial para desligamento, afastamento e fevereiro está a confirmar com
o DP.
