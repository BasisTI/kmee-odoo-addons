Integração contábil da folha de pagamento brasileira.

Este módulo estende o ``payroll_account`` (OCA) para contabilizar as verbas
salariais brasileiras, criando um diário contábil específico para a folha
(FOPAG) e entregando o mapeamento regra->conta pronto para uso.

Mapeamento entregue
-------------------

Cada regra salarial é ligada a uma conta *lógica* (slot), resolvida no plano de
contas já carregado na empresa: o módulo nunca cria contas. Num plano
brasileiro (``l10n_br_coa_generic``) cada tributo encontra a sua conta
(``INSS a Recolher``, ``FGTS a Recolher``, ``Férias a Pagar``,
``Encargos Sociais``); num plano genérico tudo cai numa despesa e num passivo,
como antes.

============================  ==============================  ==========================
Rubrica                       Débito (despesa)                Crédito (passivo)
============================  ==============================  ==========================
Salário base                  Salários                        (contrapartida do líquido)
INSS / IRRF do empregado      -                               INSS / IRRF a recolher
Salário líquido               -                               Salários a pagar
FGTS                          Encargos sociais                FGTS a recolher
FGTS (férias, 13º, rescisão)  Encargos sociais                FGTS a recolher
CPP (patronal 20%)            Encargos sociais                INSS a recolher
RAT ajustado                  Encargos sociais                INSS a recolher
Terceiros (FPAS)              Encargos sociais                Terceiros a recolher
Provisão de férias + 1/3      Provisão de férias              Férias a pagar
Encargos sobre férias         Provisão de férias              Férias a pagar
Provisão de 13º               Provisão de 13º                 13º salário a pagar
Encargos sobre 13º            Provisão de 13º                 13º salário a pagar
============================  ==============================  ==========================

O FGTS das estruturas do ``l10n_br_hr_vacation`` (férias, 13º 1ª e 2ª parcelas,
13º e saldo de salário da rescisão, aviso prévio indenizado) tem o mesmo
lançamento do FGTS mensal. O ``l10n_br_hr_vacation`` não é dependência: sem ele
instalado o mapa ignora essas regras, e se ele for instalado depois as contas
são vinculadas no carregamento das regras. Em banco que já tinha este módulo, a
migração 18.0.1.1.0 preenche as contas das regras de FGTS. As demais rubricas
dessas estruturas (proventos, descontos, multa do FGTS) continuam sem conta até
a decisão contábil sobre elas.

Como os encargos patronais e as provisões têm os dois lados, o custo do
empregador passa a aparecer no resultado (e a variar conforme o regime
tributário da empresa), sem afetar o líquido do empregado.

O mapeamento é idempotente e não-destrutivo: só preenche contas ainda vazias,
respeitando qualquer configuração manual feita pelo contador.

Limitação conhecida: contabilização multiempresa
------------------------------------------------

No Odoo 16 os campos ``hr.salary.rule.account_debit`` / ``account_credit`` NÃO
são dependentes de empresa, então o mapeamento vale para uma empresa por vez (a
dona do diário FOPAG). Em base multiempresa, as contas das demais empresas
precisam ser configuradas manualmente, e confirmar um holerite de outra empresa
sem essa configuração registraria o custo na empresa errada.

Para reduzir o risco, o holerite de outra empresa não nasce no diário de folha
desta: quando existe diário na empresa do holerite, ele é usado; quando não
existe, o holerite fica sem contabilização em vez de contabilizar no lugar
errado. É por isso que os lotes de demonstração por regime tributário ficam
calculados e abertos, e não confirmados.
