# Copyright (c) 2026, Nextash and contributors
# For license information, please see license.txt

import frappe
from frappe.utils import add_days, getdate, nowdate

FILE_FIELDS = (
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
)


def cleanup_old_import_files():
	"""Daily job: delete attached files on completed imports older than auto_delete_files_after_days."""
	docs = frappe.get_all(
		"Mubtkir Import Tool",
		filters={
			"status": ["in", ["Completed", "Completed with Errors"]],
			"auto_delete_files_after_days": [">", 0],
		},
		fields=["name", "modified", "auto_delete_files_after_days"],
	)
	today = getdate(nowdate())
	for row in docs:
		cutoff = add_days(today, -int(row.auto_delete_files_after_days))
		if getdate(row.modified) > cutoff:
			continue

		doc = frappe.get_doc("Mubtkir Import Tool", row.name)
		file_urls = [doc.get(f) for f in FILE_FIELDS if doc.get(f)]
		if not file_urls:
			continue

		attached_files = frappe.get_all(
			"File",
			filters={
				"attached_to_doctype": "Mubtkir Import Tool",
				"attached_to_name": doc.name,
			},
			pluck="name",
		)
		for file_name in attached_files:
			frappe.delete_doc("File", file_name, ignore_permissions=True)

		for f in FILE_FIELDS:
			if doc.get(f):
				doc.set(f, None)
		doc.save(ignore_permissions=True)
