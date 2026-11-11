**Proporcionalidade do salário**

O ``SALARIO_BASE`` e o adicional de periculosidade saem proporcionais aos dias de
salário do mês (mês comercial de 30 dias):

* admissão no mês: dias corridos até o fim do mês (teto de 30);
* desligamento no mês: dias corridos até a data final do contrato;
* afastamento previdenciário: marque *Afastamento Previdenciário* no tipo de
  ausência. A empresa paga os 15 primeiros dias e os seguintes, aprovados, saem do
  salário (são pagos pelo INSS).

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
* Em banco existente a atualização liga as rubricas à estrutura CLT. Se a
  estrutura já tem uma rubrica ``DSR_HE`` (como a do
  ``l10n_br_hr_payroll_attendance``), ela é mantida.
