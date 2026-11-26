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

function run_validate(frm) {
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
}

function run_start_import(frm) {
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
}

function run_stop_import(frm) {
	frappe.confirm(__("Are you sure you want to stop the running import?"), () => {
		frappe.call({
			method: "stop_import",
			doc: frm.doc,
			freeze: true,
			callback() {
				frm.reload_doc();
			},
		});
	});
}

function export_import_logs(frm) {
	const headers = ["Stage", "Row", "Daftra Ref", "Severity", "Message"];
	const escape_csv = (v) => `"${String(v ?? "").replace(/"/g, '""')}"`;
	const lines = [headers.map(escape_csv).join(",")];
	(frm.doc.import_logs || []).forEach((row) => {
		lines.push(
			[row.stage, row.row_number, row.reference_no, row.severity, row.message]
				.map(escape_csv)
				.join(",")
		);
	});
	const blob = new Blob(["\ufeff" + lines.join("\n")], {
		type: "text/csv;charset=utf-8;",
	});
	const url = URL.createObjectURL(blob);
	const a = document.createElement("a");
	a.href = url;
	a.download = `${frm.doc.name}_import_logs.csv`;
	document.body.appendChild(a);
	a.click();
	document.body.removeChild(a);
	URL.revokeObjectURL(url);
}

frappe.ui.form.on("Mubtkir Import Tool", {
	onload(frm) {
		frm.set_query("reference_doctype", () => ({
			filters: {
				name: ["in", ["Item", "Customer", "Supplier", "Purchase Invoice", "Sales Invoice"]],
			},
		}));
		frm.set_query("default_item_group", () => ({ filters: { is_group: 0 } }));
		frm.set_query("default_customer_group", () => ({ filters: { is_group: 0 } }));
		frm.set_query("default_supplier_group", () => ({ filters: { is_group: 0 } }));

		frappe.realtime.on("mubtkir_import_progress", (data) => {
			if (!data || data.docname !== frm.doc.name) return;
			if (data.done) {
				frm.dashboard.hide_progress();
				frm.reload_doc();
				return;
			}
			if (data.stage_done) {
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
		const is_importing = frm.doc.status === "Importing";
		const has_logs = !!(frm.doc.import_logs && frm.doc.import_logs.length > 0);

		let action_bar_html = "";
		if (frm.is_new()) {
			action_bar_html = `<div class="text-muted small" style="margin-top: 8px;">${__("Please save the document first to enable Validate and Start Import buttons.")}</div>`;
		} else {
			const btns = [];
			if (!is_importing) {
				btns.push(`<button type="button" class="btn btn-default btn-sm mit-btn-validate">${__("Validate Data")}</button>`);
				btns.push(`<button type="button" class="btn btn-primary btn-sm mit-btn-start">${__("Start Import")}</button>`);
			} else {
				btns.push(`<button type="button" class="btn btn-danger btn-sm mit-btn-stop">${__("Stop Import")}</button>`);
			}
			if (has_logs) {
				btns.push(`<button type="button" class="btn btn-default btn-sm mit-btn-export">${__("Export Logs")}</button>`);
			}
			action_bar_html = `<div style="display:flex; flex-wrap:wrap; gap:8px; margin-top:10px;">${btns.join("")}</div>`;
		}

		const warning_html = `
			<div class="alert alert-warning" style="margin-bottom: 10px; ${border_prop}: 4px solid #f0ad4e; text-align: ${align};">
				<strong>${__("Important Notice Before Import:")}</strong>
				${__("It is strongly recommended to take a site backup before starting the import and between each stage:")}
				<br>
				<span style="font-weight: 600;">${__("1. Products (Items) -> 2. Customers & Suppliers -> 3. Purchase Invoices -> 4. Sales Invoices")}</span>
				<br>
				<small>${__("So you can easily restore the backup if needed.")}</small>
				${action_bar_html}
			</div>
		`;
		if (frm.fields_dict.backup_warning_html) {
			const $wrap = frm.fields_dict.backup_warning_html.$wrapper;
			$wrap.html(warning_html);
			$wrap.find(".mit-btn-validate").on("click", () => run_validate(frm));
			$wrap.find(".mit-btn-start").on("click", () => run_start_import(frm));
			$wrap.find(".mit-btn-stop").on("click", () => run_stop_import(frm));
			$wrap.find(".mit-btn-export").on("click", () => export_import_logs(frm));
		}

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

		if (!frm.is_new() && !is_importing) {
			frm.add_custom_button(__("Validate Data"), () => run_validate(frm));
			frm.add_custom_button(__("Start Import"), () => run_start_import(frm)).addClass("btn-primary");
		} else if (!frm.is_new() && is_importing) {
			frm.add_custom_button(__("Stop Import"), () => run_stop_import(frm)).addClass("btn-danger");
		}

		if (!frm.is_new() && has_logs) {
			frm.add_custom_button(__("Export Logs"), () => export_import_logs(frm));
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
