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
