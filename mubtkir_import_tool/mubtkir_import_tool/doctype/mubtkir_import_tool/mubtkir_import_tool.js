// Copyright (c) 2024, Nextash and contributors
// For license information, please see license.txt

frappe.ui.form.on("Mubtkir Import Tool", {
	onload: function (frm) {
        frm.set_query('reference_doctype', function () {
            return {
                filters: {
                    name: ['in', ['Sales Invoice', 'Sales Order','Purchase Invoice']]
                }
            };
        });
        frm.set_df_property("sales_taxes_and_charges_template", "hidden",true);
        frm.set_df_property("purchase_taxes_and_charges", "hidden",true);
    },
    reference_doctype(frm) {
    const ref = frm.doc.reference_doctype;

    const show_sales = ["Sales Invoice", "Sales Order"].includes(ref);
    const show_purchase = ref === "Purchase Invoice";

    // Sales template field
    frm.set_df_property("sales_taxes_and_charges_template", "hidden", !show_sales);
    frm.set_df_property("sales_taxes_and_charges_template", "reqd", show_sales);

    // Purchase template field
    frm.set_df_property("purchase_taxes_and_charges", "hidden", !show_purchase);
    frm.set_df_property("purchase_taxes_and_charges", "reqd", show_purchase);
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
	},
});
