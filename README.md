
<!-- /!\ Non OCA Context : Set here the badge of your runbot / runboat instance. -->
[![Pre-commit Status](https://github.com/KMEE/kmee-odoo-addons/actions/workflows/pre-commit.yml/badge.svg?branch=18.0)](https://github.com/KMEE/kmee-odoo-addons/actions/workflows/pre-commit.yml?query=branch%3A18.0)
[![Build Status](https://github.com/KMEE/kmee-odoo-addons/actions/workflows/test.yml/badge.svg?branch=18.0)](https://github.com/KMEE/kmee-odoo-addons/actions/workflows/test.yml?query=branch%3A18.0)
[![codecov](https://codecov.io/gh/KMEE/kmee-odoo-addons/branch/18.0/graph/badge.svg)](https://codecov.io/gh/KMEE/kmee-odoo-addons)
<!-- /!\ Non OCA Context : Set here the badge of your translation instance. -->

<!-- /!\ do not modify above this line -->

# KMEE Odoo Addons

Welcome to our repository, dedicated to incubating OCA modules developed by KMEE. Our goal is to foster innovation and enhance the functionality of Odoo with cutting-edge solutions tailored to meet the diverse needs of businesses. By leveraging our expertise and commitment to quality, we aim to contribute robust and efficient modules that seamlessly integrate into the OCA ecosystem, driving productivity and growth for users worldwide.

Requisitos do l10n-brazil
-------------------------

Os módulos de folha deste fork leem o CPF do empregado em `hr.employee.vat` (campo do
`l10n_br_hr` da OCA/l10n-brazil, que guarda só os dígitos) e o mostram por `vat_formatted_cnpj`.
Isso exige **`l10n_br_hr` >= 18.0.1.8.0.2** (wheel; no git, o commit `05571fdb4` do
OCA/l10n-brazil, quando o manifest ainda dizia 1.8.0). Testado com 18.0.1.8.0.2 e 18.0.1.8.1.
Com um `l10n_br_hr` mais antigo (`cnpj_cpf`/`cpf` no empregado) o `l10n_br_hr_payroll` recusa o
carregamento com uma mensagem que diz qual versão instalar.

### Atualizar um banco que está no `l10n_br_hr` 18.0.1.6.0 (CPF em `cnpj_cpf`)

A OCA tem a migração, mas ela não roda sozinha:

1. O `-u` precisa **incluir o `l10n_br_hr`** (`-u l10n_br_hr,l10n_br_hr_payroll,...`). Só com os
   módulos de folha o servidor não sobe (`Field "cpf" does not exist in model "hr.employee"`).
2. O `pre-migrate` 18.0.1.7.0 do `l10n_br_hr` importa `openupgradelib`, que nem a wheel nem o
   manifest dele declaram: instale `openupgradelib` na imagem (`ModuleNotFoundError` sem ele).
3. A migração copia o `cnpj_cpf` para o `vat` do contato de trabalho e remove a coluna, mas **pula**
   CPF inválido, repetido (já usado por outro parceiro) e de contato que já tem `vat`. Esses
   empregados ficam sem CPF (log só em INFO). Confira antes quantos são.
4. Se o servidor subir com a coluna `hr_employee.cnpj_cpf` ainda com CPF, o `l10n_br_hr_payroll`
   recusa o carregamento e manda rodar o item 1.

Limites do `l10n_br_hr` novo, sem tratamento neste fork:

- o CPF fica no `res.partner` do contato de trabalho (`vat`), que não tem `groups`: qualquer usuário
  interno o lê pelo parceiro, ao contrário do `cnpj_cpf` antigo, restrito ao grupo de RH;
- o CPF é único por parceiro: a mesma pessoa não pode ter duas fichas de empregado com contatos
  distintos e o mesmo CPF;
- `vat_formatted_cnpj` depende da nacionalidade (`country_id`): estrangeiro com CPF sai sem
  pontuação; um `vat` importado com espaço nas pontas fica gravado com o espaço (o CAGED e a DIRF já
  eram assim).

Available addons
----------------
Addon | Description
--- | --- 
[account_payment_currency_rate](account_payment_currency_rate) | ---
[account_statement_import_ofx_invert_type](account_statement_import_ofx_invert_type) | It allows you to reverse transactions from debit to credit and vice versa, and also ignore the balance.
[hr_holidays_allocation_plan](hr_holidays_allocation_plan) | ---
[hr_holidays_no_mail](hr_holidays_no_mail) | Hr Holiday No Mail
[hr_holidays_plan_next_year](hr_holidays_plan_next_year) | ---
[hr_holidays_required_support_document](hr_holidays_required_support_document) | It adds an boolean that forces the supported document when approving the day off.
[hr_leave_allocation_multiple_tags](hr_leave_allocation_multiple_tags) | ---
[hr_recruitment_job_share](hr_recruitment_job_share) | It allows the user to share details of a job that has not been published on the site yet.
[hr_recruitment_reject_mail_editable](hr_recruitment_reject_mail_editable) | It enables the user to edit the email that will be sent to the rejected candidate.
[hr_work_entry_holidays_natural_period](hr_work_entry_holidays_natural_period) | Fix hr_holidays_natural_period when hr_work_entry_holidays is installed.
[l10n_br_account_statement_import_txt_xlsx](l10n_br_account_statement_import_txt_xlsx) | Contains the statement map of ITAU, SANTANDER, SICRED and BTG banks.
[l10n_br_hr_holidays_public](l10n_br_hr_holidays_public) | Implements integration between public holidays and the Brazilian resource calendar.
[l10n_br_hr_overtime_custom_multiplier](l10n_br_hr_overtime_custom_multiplier) | Module allows companies to apply a custom multiplier to overtime calculations in the Brazilian localization, providing flexible and configurable overtime management.
[l10n_br_hr_recruitment](l10n_br_hr_recruitment) | This module implements the localization fields found on the employee on the applicant module, to garantee that employee created from the application has all information.
[l10n_br_sale_report_py3o](l10n_br_sale_report_py3o) | Contains the sale order report in py3o format.
[l10n_br_stock_report_py3o](l10n_br_stock_report_py3o) | Contains the stock picking report in py3o format.
[l10n_br_website_hr_recruitment_form](l10n_br_website_hr_recruitment_form) | This module adds an public application form on the website.
[mail_no_reply](mail_no_reply) | It adds two fields: an email in the reply in the company configuration and a boolean in the mail template that adds this email in the reply as sending and as a reply email.
[partner_display_name_ref](partner_display_name_ref) | Displays the partner's name in the format "[ref] name".
[project_task_service_class](project_task_service_class) | Allows you to define service classes for tasks.
[project_tech_lead](project_tech_lead) | Creates the Tech Lead field for tasks and projects.
[sale_crm_auto_won](sale_crm_auto_won) | Assigns the opportunity stage to "Won" when this opportunity has generated a sale.
[sale_hide_internal_reference](sale_hide_internal_reference) | Allows you to hide the internal reference of the product.
[sale_partial_lock](sale_partial_lock) | Allows you to create invoices even when a sale order is locked.
[stock_intercompany_bidirectional_pull](stock_intercompany_bidirectional_pull) | When an inbound transfer is created, "Marked as To Do" and the contact is a multi-company company, in that company, a outbound transfer is created.
[website_hr_recruitment_display_description](website_hr_recruitment_display_description) | This module inserts the job description on the website, just below the location.

<!-- /!\ do not modify below this line -->

<!-- prettier-ignore-start -->

[//]: # (addons)
[//]: # (end addons)

<!-- prettier-ignore-end -->

## Licenses

This repository is licensed under [LGPL-3.0](LICENSE).

----
<!-- /!\ Non OCA Context : Set here the full description of your organization. -->
