Holerite e relatórios da folha de pagamento brasileira.

Substitui o relatório genérico de payslip da OCA por um holerite
com layout brasileiro:

* Cabeçalho com dados da empresa (CNPJ, endereço)
* Dados do empregado (CPF, PIS/PASEP, cargo, departamento)
* Proventos e descontos em colunas separadas, sem o subtotal da remuneração
  bruta nem as provisões e encargos patronais, que não são verba paga
* Totais de proventos e de descontos, e o líquido
* Quadro de bases: salário de contribuição do INSS, base do IRRF, base do FGTS e FGTS
  do mês. No 13º e na rescisão, o INSS e o IRRF do 13º têm base própria
* Rubricas informativas (inclusive a multa do FGTS) fora das colunas de valor

O relatório "Holerite" da OCA (``payroll.action_report_payslip``) deixa de aparecer
no menu Imprimir do holerite, para o usuário não ver dois com o mesmo nome. O
relatório continua instalado, porque o módulo ``payroll`` o usa no envio por e-mail.

Recibo de férias
~~~~~~~~~~~~~~~~

O recibo traz o período aquisitivo (o da alocação de férias) e o período de gozo
(início, fim, retorno ao trabalho e data limite de pagamento, CLT art. 145), os
dias vendidos no abono pecuniário, a remuneração de referência (salário, média das
variáveis habituais e adicionais fixos), proventos e descontos nas colunas, o líquido
e o quadro de bases, no mesmo padrão do contracheque. No fracionamento, indica o
período (1 de 3, por exemplo).

Aviso de férias
~~~~~~~~~~~~~~~

O relatório "Aviso de Férias" é o comunicado por escrito do art. 135 da CLT, emitido
a partir do holerite de férias: período de gozo, retorno, data limite de comunicação
(30 dias antes do início) e campo de ciência do empregado. Se emitido com menos de
30 dias de antecedência, sai marcado como fora do prazo, sem bloquear a impressão.
