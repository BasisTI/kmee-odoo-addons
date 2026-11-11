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
