// Copyright (c) 2024, Nextash and contributors
// For license information, please see license.txt

frappe.ui.form.on("Mubtkir Import", {
	onload_post_render(frm) {
		frm.trigger("update_primary_action");
	},
	update_primary_action(frm) {
		if (frm.is_dirty()) {
			frm.enable_save();
			return;
		}
		frm.disable_save();
		if (frm.doc.status !== "Success") {
			if (!frm.is_new() && frm.has_import_file()) {
				let label = frm.doc.status === "Pending" ? __("Start Import") : __("Retry");
				frm.page.set_primary_action(label, () => frm.events.start_import(frm));
			} else {
				frm.page.set_primary_action(__("Save"), () => frm.save());
			}
		}
	},
	refresh: function (frm) {
		frm.get_field("import_file").df.options = {
			restrictions: {
				allowed_file_types: [".csv", ".xls", ".xlsx"],
			},
		};
		frm.get_field("child_table").df.options = {
			restrictions: {
				allowed_file_types: [".csv", ".xls", ".xlsx"],
			},
		};
		// if (!frm.is_new()) {
		//     frm.add_custom_button('Preview Data', () => {
		//         frappe.call({
		//             method: "mubtkir_import_tool.mubtkir_import_tool.doctype.mubtkir_import.mubtkir_import.preview_data",
		//             args: {
		//                 docname: frm.doc.name
		//             },
		//             callback: function (response) {
		//                 if (response.message) {
		//                     frm.set_df_property("mubtkir_import_preview", "options", response.message);
		//                     frm.refresh_field("mubtkir_import_preview");
		//                 }
		//             }
		//         });
		//     });
		// }
		// if (frm.doc.status === "Validating") {
		//     frm.add_custom_button('Import Data', () => {
		//         frappe.call({
		//             method: "mubtkir_import_tool.mubtkir_import_tool.doctype.mubtkir_import.mubtkir_import.import_data",
		//             args: {
		//                 docname: frm.doc.name
		//             },
		//             callback: function () {
		//                 frm.reload_doc();
		//             }
		//         });
		//     });
		// }
		frm.has_import_file = () => {
			return frm.doc.import_file || frm.doc.child_table;
		};
	},
	import_file(frm) {
		frm.toggle_display("section_import_preview", frm.has_import_file());
		console.log(frm.has_import_file());
		if (!frm.has_import_file()) {
			frm.get_field("mubtkir_import_preview").$wrapper.empty();
			return;
		}
		else {
			frm.trigger("update_primary_action");
		}

		// load import preview
		frm.get_field("mubtkir_import_preview").$wrapper.empty();
		$('<span class="text-muted">')
			.html(__("Loading import file..."))
			.appendTo(frm.get_field("mubtkir_import_preview").$wrapper);

		frappe.call({
			// mubtkir_import_tool.mubtkir_import_tool.doctype.mubtkir_import.mubtkir_import.get_preview_from_template
			method: "mubtkir_import_tool.mubtkir_import_tool.doctype.mubtkir_import.mubtkir_import.get_preview_from_template",
			args: {
				data_import: frm.doc.name,
				import_file: frm.doc.import_file,
				google_sheets_url: frm.doc.google_sheets_url,
			},
			error_handlers: {
				TimestampMismatchError() {
				},
			},
		}).then((r) => {
			let preview_data = r.message;
			console.log(r);

			frm.events.show_import_preview(frm, preview_data);
			// frm.events.show_import_warnings(frm, preview_data);
		});
	},

	show_import_preview(frm, preview_data) {
		let import_log = preview_data.import_log;

		if (frm.import_preview && frm.import_preview.doctype === frm.doc.reference_doctype) {
			frm.import_preview.preview_data = preview_data;
			frm.import_preview.import_log = import_log;
			frm.import_preview.refresh();
			return;
		}

		frappe.require("data_import_tools.bundle.js", () => {
			frm.import_preview = new frappe.data_import.ImportPreview({
				wrapper: frm.get_field("mubtkir_import_preview").$wrapper,
				doctype: frm.doc.reference_doctype,
				preview_data,
				import_log,
				frm,
				events: {
					remap_column(changed_map) {
						let template_options = JSON.parse(frm.doc.template_options || "{}");
						template_options.column_to_field_map =
							template_options.column_to_field_map || {};
						Object.assign(template_options.column_to_field_map, changed_map);
						frm.set_value("template_options", JSON.stringify(template_options));
						frm.save().then(() => frm.trigger("import_file"));
					},
				},
			});
		});
	},
	// start_import(frm) {
	// 	frm.call({
	// 		method: "form_start_import",
	// 		args: { data_import: frm.doc.name },
	// 		btn: frm.page.btn_primary,
	// 	}).then((r) => {
	// 		if (r.message === true) {
	// 			frm.disable_save();
	// 		}
	// 	});
	// },


});
