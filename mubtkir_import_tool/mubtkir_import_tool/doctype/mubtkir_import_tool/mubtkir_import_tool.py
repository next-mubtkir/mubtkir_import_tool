# Copyright (c) 2024, Nextash and contributors
# For license information, please see license.txt

import os

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils.file_manager import get_file_path

from .daftra_parser import validate_stage_data
from .importers import (
	import_customers,
	import_invoices,
	import_items,
	import_suppliers,
)

MAX_LOG_ROWS = 500


class MubtkirImportTool(Document):
	def validate(self):
		if self.import_mode == "Single DocType" and not self.reference_doctype:
			frappe.throw(_("Please select a Reference Doctype."))

	def on_update(self):
		# Ensure all files attached to this document are public
		private_files = frappe.get_all(
			"File",
			filters={
				"attached_to_doctype": self.doctype,
				"attached_to_name": self.name,
				"is_private": 1,
			},
			pluck="name",
		)
		for fname in private_files:
			fdoc = frappe.get_doc("File", fname)
			fdoc.is_private = 0
			fdoc.save(ignore_permissions=True)

	def _resolve_path(self, file_url: str | None) -> str | None:
		if not file_url:
			return None
		path = get_file_path(file_url)
		if not os.path.exists(path):
			frappe.throw(_("Attached file not found on disk: {0}").format(file_url))
		return path

	def _get_configured_stages(self) -> list[tuple[str, str, str | None, bool]]:
		"""Return list of (stage_name, main_file_path, child_file_path, force_return) in strict order."""
		stages: list[tuple[str, str, str | None, bool]] = []
		if self.import_mode == "Single DocType":
			main_path = self._resolve_path(self.main_file)
			if not main_path:
				frappe.throw(_("Please attach the Main File (or Daftra ZIP)."))
			child_path = self._resolve_path(self.child_file)
			stages.append((self.reference_doctype, main_path, child_path, bool(self.is_return_import)))
			return stages

		stage_map = [
			("Item", self.products_file, None, False),
			("Customer", self.customers_file, self.customers_contacts_file, False),
			("Supplier", self.suppliers_file, self.suppliers_contacts_file, False),
			("Purchase Invoice", self.purchase_invoices_file, self.purchase_items_file, False),
			("Purchase Return", self.purchase_returns_file, self.purchase_returns_items_file, True),
			("Sales Invoice", self.sales_invoices_file, self.sales_items_file, False),
			("Sales Return", self.sales_returns_file, self.sales_returns_items_file, True),
		]
		for stage, main_url, child_url, force_ret in stage_map:
			if main_url:
				stages.append((stage, self._resolve_path(main_url), self._resolve_path(child_url), force_ret))

		if not stages:
			frappe.throw(_("Please attach at least one Daftra file to validate or import."))
		return stages

	def _append_logs(self, logs: list[dict]):
		for entry in logs:
			if len(self.import_logs or []) >= MAX_LOG_ROWS:
				break
			self.append("import_logs", entry)

	@frappe.whitelist()
	def validate_files(self):
		"""Dry-run validation of all attached Daftra files without writing target records."""
		if not self.has_permission("write"):
			frappe.throw(_("Not permitted to validate import files."), frappe.PermissionError)

		stages = self._get_configured_stages()
		self.status = "Validating"
		self.set("import_logs", [])

		total_all = 0
		valid_all = 0
		error_count = 0
		summary_lines: list[str] = []

		for stage, main_path, child_path, force_ret in stages:
			res = validate_stage_data(
				stage=stage,
				main_file_path=main_path,
				child_file_path=child_path,
				tax_mode=self.tax_mode or "Both (Auto-detect per row)",
				force_return=force_ret,
			)
			total_all += res["total_records"]
			valid_all += res["valid_records"]
			stage_errors = sum(1 for l in res["logs"] if l["severity"] == "Error")
			error_count += stage_errors
			summary_lines.append(
				_("{0}: {1}/{2} valid ({3} errors)").format(
					_(stage), res["valid_records"], res["total_records"], stage_errors
				)
			)
			self._append_logs(res["logs"])

		self.total_records = total_all
		self.valid_records = valid_all
		self.validation_summary = "\n".join(summary_lines)
		self.status = "Validation Failed" if error_count > 0 else "Validated"
		self.save()
		return {
			"status": self.status,
			"total_records": self.total_records,
			"valid_records": self.valid_records,
			"error_count": error_count,
			"summary": self.validation_summary,
		}

	@frappe.whitelist()
	def start_import(self):
		"""Enqueue the import job in the background long queue."""
		if not self.has_permission("write"):
			frappe.throw(_("Not permitted to start import."), frappe.PermissionError)
		if self.status == "Importing":
			frappe.throw(_("Import is already running in the background."))

		stages = self._get_configured_stages()
		stage_names = {s[0] for s in stages}
		if ({"Sales Invoice", "Sales Return"} & stage_names) and not self.sales_taxes_and_charges_template:
			frappe.throw(_("Please select a Sales Taxes and Charges Template before importing Sales Invoices."))
		if ({"Purchase Invoice", "Purchase Return"} & stage_names) and not self.purchase_taxes_and_charges:
			frappe.throw(_("Please select a Purchase Taxes and Charges Template before importing Purchase Invoices."))

		self.status = "Importing"
		self.imported_records = 0
		self.skipped_records = 0
		self.failed_records = 0
		self.set("import_logs", [])
		self.save()

		frappe.enqueue_doc(
			self.doctype,
			self.name,
			"run_import_job",
			queue="long",
			timeout=3600,
			enqueue_after_commit=True,
			job_id=f"mubtkir_import_{self.name}",
			deduplicate=True,
		)
		return {"status": "Importing", "message": _("Import job enqueued.")}

	def run_import_job(self):
		"""Background worker method executing stages in strict dependency order."""
		try:
			stages = self._get_configured_stages()
			total_imported = 0
			total_skipped = 0
			total_failed = 0
			total_records = 0
			summary_lines: list[str] = []
			all_logs: list[dict] = []

			for stage, main_path, child_path, force_ret in stages:
				def publish_progress(current, total, st=stage):
					frappe.publish_realtime(
						"mubtkir_import_progress",
						{
							"docname": self.name,
							"stage": _(st),
							"current": current,
							"total": total,
						},
						user=self.modified_by,
					)

				if stage == "Item":
					res = import_items(
						main_path,
						child_path,
						skip_existing=bool(self.skip_existing),
						item_group=self.default_item_group,
						progress_cb=publish_progress,
					)
				elif stage == "Customer":
					res = import_customers(
						main_path,
						child_path,
						skip_existing=bool(self.skip_existing),
						customer_group=self.default_customer_group,
						progress_cb=publish_progress,
					)
				elif stage == "Supplier":
					res = import_suppliers(
						main_path,
						child_path,
						skip_existing=bool(self.skip_existing),
						supplier_group=self.default_supplier_group,
						progress_cb=publish_progress,
					)
				elif stage in ("Purchase Invoice", "Purchase Return"):
					res = import_invoices(
						stage=stage,
						main_file_path=main_path,
						child_file_path=child_path,
						company=self.company,
						tax_mode=self.tax_mode or "Both (Auto-detect per row)",
						tax_template=self.purchase_taxes_and_charges,
						submit_invoices=bool(self.submit_invoices),
						update_stock=bool(self.update_stock),
						skip_existing=bool(self.skip_existing),
						force_return=force_ret,
						default_item_group=self.default_item_group,
						default_supplier_group=self.default_supplier_group,
						max_records=int(self.max_records_per_run or 0),
						progress_cb=publish_progress,
					)
				elif stage in ("Sales Invoice", "Sales Return"):
					res = import_invoices(
						stage=stage,
						main_file_path=main_path,
						child_file_path=child_path,
						company=self.company,
						tax_mode=self.tax_mode or "Both (Auto-detect per row)",
						tax_template=self.sales_taxes_and_charges_template,
						submit_invoices=bool(self.submit_invoices),
						update_stock=bool(self.update_stock),
						skip_existing=bool(self.skip_existing),
						force_return=force_ret,
						default_item_group=self.default_item_group,
						default_customer_group=self.default_customer_group,
						max_records=int(self.max_records_per_run or 0),
						progress_cb=publish_progress,
					)
				else:
					continue

				total_records += res["total"]
				total_imported += res["imported"]
				total_skipped += res["skipped"]
				total_failed += res["failed"]
				all_logs.extend(res["logs"])
				summary_lines.append(
					_("{0}: imported={1}, skipped={2}, failed={3}").format(
						_(stage), res["imported"], res["skipped"], res["failed"]
					)
				)

			self.reload()
			self.total_records = total_records
			self.imported_records = total_imported
			self.skipped_records = total_skipped
			self.failed_records = total_failed
			self.validation_summary = "\n".join(summary_lines)
			self.set("import_logs", [])
			self._append_logs(all_logs)
			self.status = "Completed with Errors" if total_failed > 0 else "Completed"
			self.save(ignore_permissions=True)
			frappe.db.commit()
		except Exception as exc:
			frappe.log_error(frappe.get_traceback(), f"Mubtkir Import Failed: {self.name}")
			self.reload()
			self.status = "Failed"
			self.validation_summary = _("Fatal error: {0}").format(str(exc)[:300])
			self.save(ignore_permissions=True)
			frappe.db.commit()
		finally:
			frappe.publish_realtime(
				"mubtkir_import_progress",
				{"docname": self.name, "done": True},
				user=self.modified_by,
			)
