// Copyright (c) 2024, Nextash and contributors
// For license information, please see license.txt

frappe.ui.form.on("Mubtkir Import Tool", {
	onload: function (frm) {
        // Set filter for reference_doctype field
        frm.set_query('reference_doctype', function () {
            return {
                filters: {
                    name: ['in', ['Sales Invoice', 'Sales Order','Purchase Invoice']]
                }
            };
        });
        frm.set_df_property('import_account', 'hidden', true);
    },
	refresh(frm) {
        frm.get_field("main_file").df.options = {
			restrictions: {
				allowed_file_types: [".xls", ".xlsx"],
			},
		};
		frm.get_field("child_file").df.options = {
			restrictions: {
				allowed_file_types: [".xls", ".xlsx"],
			},
		};
        if (!frm.is_new()){
            frm.set_df_property('import_account', 'hidden', false);
            frm.set_query('import_account', function () {
                const default_company = frappe.defaults.get_default('company');
                return {
                    filters: {
                        account_type: ['in', ['Tax', 'Chargeable', 'Expense Account']],
                        company: default_company
                    }
                };
            });
        }
	},
	reference_doctype: function (frm) {
        if (!frm.is_new()){
        frm.set_df_property('import_account', 'reqd', true);
        frm.set_df_property('import_account', 'hidden', false);  

        frm.set_query('import_account', function () {
			const default_company = frappe.defaults.get_default('company');
            return {
                filters: {
                    account_type: ['in', ['Tax', 'Chargeable', 'Expense Account']],
					company: default_company
				}
            };
        });
    }
    },
});
