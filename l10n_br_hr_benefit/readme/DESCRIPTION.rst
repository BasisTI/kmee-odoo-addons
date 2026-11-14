Benefícios na folha de pagamento brasileira.

Integra o módulo OCA ``payroll_contract_advantages`` com as regras
salariais brasileiras, adicionando templates de benefícios comuns:

- **Vale-Transporte (VT)**: crédito pelo valor diário da tarifa
  (``VT_DIARIO``) x dias úteis do mês, e desconto do empregado limitado a 6%
  do salário-base e ao custo do VT (Lei 7.418/85, art. 4º; Decreto 10.854/21,
  art. 110)
- **Vale-Refeição (VR)**: não tributável (INSS/IRRF)
- **Vale-Alimentação (VA)**: não tributável
- **Plano de Saúde**: desconto dedutível do IRRF

Os benefícios são configurados por contrato via advantage templates
e calculados automaticamente na folha de pagamento.

**Dias úteis do VT.** Escala do calendário do contrato (inclusive o quinzenal,
como a 12x36), menos os feriados (ausência global de dia inteiro, como no DSR, e
o ``l10n_br_hr_holidays_public`` quando instalado), o recesso global de vários
dias, e os afastamentos, licenças e férias aprovados de dia inteiro. Limites:
ausência por horas e falta lançada no holerite não tiram o dia, e mudar
feriado ou afastamento não recalcula holerite já calculado. O contrato usa
``VT`` (mensal) ou ``VT_DIARIO``, nunca os dois.
