// Copyright (c) 2024, Nextash and contributors
// For license information, please see license.txt

frappe.ui.form.on("Mubtkir Import Tool", {
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
