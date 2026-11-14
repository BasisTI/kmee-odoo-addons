**CCT no contrato e nas regras salariais**

#. Cadastre a CCT em *Funcionários > Sindicato > Convenções Coletivas*, com a vigência,
   a contribuição assistencial, a mensalidade sindical, o percentual de vale-transporte,
   os dias de DSR por semana com falta, as faixas de desconto de VA/VR e os pisos.
#. No contrato, escolha a *Convenção Coletiva (CCT)*. O sindicato do contrato é o da CCT.
#. Quando vier o dissídio, cadastre a CCT seguinte do mesmo sindicato (as vigências não
   podem se sobrepor): o contrato continua apontando a primeira, e cada holerite lê a CCT
   que cobre a competência (fim do período).
#. Nas regras salariais, ``tools.br.cct(contract)`` devolve a CCT vigente (vazia sem CCT:
   a regra decide se usa a CCT ou o que usava antes) e
   ``tools.br.contribuicao_sindical(contract, 'assistencial')`` o valor da contribuição
   cadastrada para o mês. Exemplo::

       cct = tools.br.cct(contract)
       if cct:
           result = cct.assistencial_amount

**Holerites.** Mudar o que a CCT entrega às regras (valores, faixas, pisos, vigência), a
contribuição ou a CCT do contrato recalcula os holerites em rascunho ou verificação cuja
estrutura lê a CCT. Holerite confirmado ou pago guarda o que valeu: só a mudança que alteraria
um confirmado cujo contrato tem outro holerite aberto no mesmo mês é recusada (volte o
confirmado para rascunho antes).

**Sem CCT cobrindo a competência.** Vale a última CCT vencida do mesmo sindicato e o holerite
mostra o aviso com o nome e o fim da vigência dela (a decisão do que fazer na lacuna é do DP:
art. 614, §3º, da CLT e ADPF 323). Antes da primeira CCT do sindicato, o contrato segue sem CCT.
Salário acima da última faixa de VA/VR e CCT apontada por contrato apagada são recusados.

**O que o módulo não decide.** Quem paga a contribuição assistencial ou sindical
(autorização expressa do empregado, direito de oposição, art. 545 e 578 da CLT depois da
Reforma Trabalhista; STF, Tema 935) é decisão da regra salarial: o módulo só informa o valor.
