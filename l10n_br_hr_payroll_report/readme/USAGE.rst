**Aviso de férias**

O aviso é impresso da ausência de férias aprovada (Ausências > Gestão > Todas as
ausências > Imprimir > Aviso de Férias). Quem emite o aviso: Ausências: Oficial ou
superior. O perfil do DP deve incluir esse grupo (``hr_holidays.group_hr_holidays_user``);
a folha, sem ele, não vê as ausências dos empregados e não emite o aviso.

A data de comunicação é gravada na primeira emissão do período avisado. Reimprimir
repete a data. Remarcar a ausência para fora do período avisado gera comunicação nova,
medida contra a nova data. Emitir com menos de 30 dias de antecedência imprime um
alerta, sem bloquear.

**TRCT e termo de quitação**

O Termo de Rescisão (Imprimir > Termo de Rescisão, no holerite de rescisão) segue o
leiaute do anexo da Portaria MTE 1.621/2010, com os campos numerados: identificação do
empregador (01 a 07) e do trabalhador (10 a 20), dados do contrato (21 a 32: tipo, causa,
remuneração, admissão, aviso, afastamento, código do afastamento, pensão, categoria e
sindicato), verbas rescisórias (50 a 99), deduções (100 a 116), totais e líquido, mais o
termo de quitação em página própria. A Portaria MTP 671/2021 revogou a 1.621/2010 sem
publicar outro modelo, e o leiaute continua sendo a referência.

O mapeamento rubrica para campo é fixo: saldo de salário (50), 13º proporcional (63), férias
proporcionais (65) e vencidas (66.1), terço constitucional (68), aviso prévio indenizado
(69), indenização do art. 479 (61), adiantamento do 13º (102), aviso não cumprido (103),
indenização do art. 480 (104), INSS (112.1 e 112.2), IRRF (114.1 e 114.2) e pensão (100).
A rubrica sem campo vai para "Outras verbas" (95) ou "Outros descontos" (115), com o nome
dela detalhado abaixo do bloco; nada some do termo. O 13º sobre o aviso indenizado (campo
70) ainda sai dentro do 63, porque a regra o calcula junto. A multa do FGTS é informativa e
não entra nos totais. O campo 27 mostra o ``mtvDeslig`` do eSocial da causa de rescisão. Quem
imprime é o mesmo perfil do recibo de férias.
