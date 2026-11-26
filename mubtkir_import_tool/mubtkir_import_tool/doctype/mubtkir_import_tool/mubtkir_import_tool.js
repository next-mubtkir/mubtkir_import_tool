// Copyright (c) 2024, Nextash and contributors
// For license information, please see license.txt

const ALLOWED_EXTENSIONS = [".zip", ".csv", ".xls", ".xlsx"];
const FILE_FIELDS = [
	"main_file",
	"child_file",
	"products_file",
	"customers_file",
	"suppliers_file",
	"purchase_invoices_file",
	"purchase_items_file",
	"sales_invoices_file",
	"sales_items_file",
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
		// Render prominent Arabic backup reminder banner
		const warning_html = `
			<div class="alert alert-warning" style="margin-bottom: 10px; border-right: 4px solid #f0ad4e; direction: rtl; text-align: right;">
				<strong>تنبيه هام قبل الاستيراد:</strong>
				يُنصح بشدة بأخذ <strong>نسخة احتياطية (Backup)</strong> من الموقع قبل البدء في الاستيراد وبين كل مرحلة وأخرى:
				<br>
				<span style="font-weight: 600;">1. المنتجات (Items) ← 2. العملاء والموردين (Customers & Suppliers) ← 3. فواتير المشتريات (Purchase Invoices) ← 4. فواتير المبيعات (Sales Invoices)</span>
				<br>
				<small>حتى تتمكن من استرجاع النسخة بسهولة عند الحاجة.</small>
			</div>
		`;
		if (frm.fields_dict.backup_warning_html) {
			frm.fields_dict.backup_warning_html.$wrapper.html(warning_html);
		}

		// Allow ZIP, CSV, and Excel on all upload fields
		FILE_FIELDS.forEach((fieldname) => {
			const field = frm.get_field(fieldname);
			if (field) {
				field.df.options = {
					restrictions: {
						allowed_file_types: ALLOWED_EXTENSIONS,
					},
				};
			}
		});

		frm.trigger("toggle_tax_fields");

		if (!frm.is_new() && frm.doc.status !== "Importing") {
			frm.add_custom_button(__("فحص البيانات (Validate Data)"), () => {
				frappe.call({
					method: "validate_files",
					doc: frm.doc,
					freeze: true,
					freeze_message: __("جاري فحص الملفات والضرائب والإجماليات..."),
					callback(r) {
						frm.reload_doc();
						if (r.message) {
							const msg = r.message;
							const indicator = msg.error_count > 0 ? "orange" : "green";
							frappe.msgprint({
								title: __("نتيجة فحص البيانات"),
								indicator,
								message: `<pre style="white-space: pre-wrap;">${frappe.utils.escape_html(msg.summary || "")}</pre>`,
							});
						}
					},
				});
			});

			frm.add_custom_button(__("بدء الاستيراد (Start Import)"), () => {
				frappe.confirm(
					__(
						"هل قمت بأخذ نسخة احتياطية (Backup) من الموقع قبل بدء الاستيراد؟ سيتم حفظ الفواتير واعتمادها وفق الإعدادات المحددة."
					),
					() => {
						frappe.call({
							method: "start_import",
							doc: frm.doc,
							freeze: true,
							freeze_message: __("جاري تشغيل مهمة الاستيراد في الخلفية..."),
							callback() {
								frm.reload_doc();
								frappe.show_alert({
									message: __("بدأ الاستيراد في الخلفية، سيتم تحديث التقدم تلقائياً."),
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
	},
});
