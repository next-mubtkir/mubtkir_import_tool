// Copyright (c) 2024, Nextash and contributors
// For license information, please see license.txt

const ALLOWED_EXTENSIONS = [".zip", ".csv", ".xls", ".xlsx"];
const FILE_FIELDS = [
	"main_file",
	"child_file",
	"products_file",
	"customers_file",
	"customers_contacts_file",
	"suppliers_file",
	"suppliers_contacts_file",
	"purchase_invoices_file",
	"purchase_items_file",
	"purchase_returns_file",
	"purchase_returns_items_file",
	"sales_invoices_file",
	"sales_items_file",
	"sales_returns_file",
	"sales_returns_items_file",
];

frappe.ui.form.on("Mubtkir Import Tool", {
	onload(frm) {
		frm.set_query("reference_doctype", () => ({
			filters: {
				name: ["in", ["Item", "Customer", "Supplier", "Purchase Invoice", "Sales Invoice"]],
			},
		}));

		frappe.realtime.on("mubtkir_import_progress", (data) => {
			if (!data || data.docname !== frm.doc.name) return;
			if (data.done) {
				frm.dashboard.hide_progress();
				frm.reload_doc();
				return;
			}
			if (data.total) {
				frm.dashboard.show_progress(
					__("Importing {0}", [data.stage]),
					(data.current / data.total) * 100,
					__("{0} / {1}", [data.current, data.total])
				);
			}
		});
	},

	refresh(frm) {
		const is_rtl = frappe.utils.is_rtl();
		const border_prop = is_rtl ? "border-right" : "border-left";
		const align = is_rtl ? "right" : "left";

		const warning_html = `
			<div class="alert alert-warning" style="margin-bottom: 10px; ${border_prop}: 4px solid #f0ad4e; text-align: ${align};">
				<strong>${__("Important Notice Before Import:")}</strong>
				${__("It is strongly recommended to take a site backup before starting the import and between each stage:")}
				<br>
				<span style="font-weight: 600;">${__("1. Products (Items) -> 2. Customers & Suppliers -> 3. Purchase Invoices -> 4. Sales Invoices")}</span>
				<br>
				<small>${__("So you can easily restore the backup if needed.")}</small>
			</div>
		`;
		if (frm.fields_dict.backup_warning_html) {
			frm.fields_dict.backup_warning_html.$wrapper.html(warning_html);
		}

		// Force Public attachments and allowed file types on all upload fields
		FILE_FIELDS.forEach((fieldname) => {
			const field = frm.get_field(fieldname);
			if (field) {
				field.df.options = {
					make_attachments_public: 1,
					restrictions: {
						allowed_file_types: ALLOWED_EXTENSIONS,
					},
				};
			}
		});

		frm.trigger("toggle_tax_fields");

		if (!frm.is_new() && frm.doc.status !== "Importing") {
			frm.add_custom_button(__("Validate Data"), () => {
				frappe.call({
					method: "validate_files",
					doc: frm.doc,
					freeze: true,
					freeze_message: __("Validating files, taxes, and totals..."),
					callback(r) {
						frm.reload_doc();
						if (r.message) {
							const msg = r.message;
							const indicator = msg.error_count > 0 ? "orange" : "green";
							frappe.msgprint({
								title: __("Validation Result"),
								indicator,
								message: `<pre style="white-space: pre-wrap;">${frappe.utils.escape_html(msg.summary || "")}</pre>`,
							});
						}
					},
				});
			});

			frm.add_custom_button(__("Start Import"), () => {
				frappe.confirm(
					__(
						"Have you taken a site backup before starting the import? Invoices will be saved and submitted automatically according to your settings."
					),
					() => {
						frappe.call({
							method: "start_import",
							doc: frm.doc,
							freeze: true,
							freeze_message: __("Enqueueing background import job..."),
							callback() {
								frm.reload_doc();
								frappe.show_alert({
									message: __("Import started in the background; progress will update automatically."),
									indicator: "blue",
								});
							},
						});
					}
				);
			}).addClass("btn-primary");
		}
	},

	import_mode(frm) {
		frm.trigger("toggle_tax_fields");
	},

	reference_doctype(frm) {
		frm.trigger("toggle_tax_fields");
	},

	toggle_tax_fields(frm) {
		const is_full = frm.doc.import_mode === "Full Migration";
		const ref = frm.doc.reference_doctype;

		const show_sales = is_full || ref === "Sales Invoice";
		const show_purchase = is_full || ref === "Purchase Invoice";

		frm.set_df_property("sales_taxes_and_charges_template", "hidden", !show_sales);
		frm.set_df_property("purchase_taxes_and_charges", "hidden", !show_purchase);

		frm.set_df_property("default_item_group", "hidden", !(is_full || ["Item", "Sales Invoice", "Purchase Invoice"].includes(ref)));
		frm.set_df_property("default_customer_group", "hidden", !(is_full || ["Customer", "Sales Invoice"].includes(ref)));
		frm.set_df_property("default_supplier_group", "hidden", !(is_full || ["Supplier", "Purchase Invoice"].includes(ref)));
	},
});
