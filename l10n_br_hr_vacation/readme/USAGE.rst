**Saldo de salário na rescisão e holerite mensal do mesmo período**

O SALDO_SALARIO da rescisão desconta o salário que o holerite mensal do mesmo
período já pagou, para que os dias não sejam pagos duas vezes. O vínculo é
mantido pelas próprias ações, sem recálculo manual:

* calcular, cancelar ou excluir o holerite mensal recalcula a rescisão que
  ainda está em rascunho/verificação;
* se a rescisão já está confirmada e a ação mudaria o salário pago pelo
  mensal, a ação é recusada com mensagem: volte a rescisão para rascunho
  primeiro, faça a alteração no mensal e recalcule/confirme a rescisão.
