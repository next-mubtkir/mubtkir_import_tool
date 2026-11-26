# Copyright (c) 2026, Nextash and contributors
# For license information, please see license.txt

import csv
import io
import os
import zipfile
from datetime import date, datetime

from frappe import _
from frappe.utils import flt


def clean_cell(value) -> str:
	"""Normalize a CSV/Excel cell value, stripping UTF-8 BOM and whitespace."""
	if value is None:
		return ""
	if isinstance(value, float) and value != value:  # NaN check
		return ""
	text = str(value).replace("\ufeff", "").strip()
	if len(text) >= 2 and text.startswith('"') and text.endswith('"'):
		text = text[1:-1].strip()
	return text


def parse_date_str(value) -> str | None:
	"""Parse Daftra date (YYYY-MM-DD, MM/DD/YYYY, DD/MM/YYYY, or datetime) to YYYY-MM-DD."""
	if isinstance(value, datetime):
		return value.strftime("%Y-%m-%d")
	if isinstance(value, date):
		return value.strftime("%Y-%m-%d")
	text = clean_cell(value)
	if not text:
		return None
	for fmt in ("%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%m/%d/%Y", "%d/%m/%Y", "%Y/%m/%d"):
		try:
			return datetime.strptime(text, fmt).strftime("%Y-%m-%d")
		except ValueError:
			continue
	return None


def _decode_bytes(raw_bytes: bytes) -> str:
	for encoding in ("utf-8-sig", "utf-8", "cp1256", "latin-1"):
		try:
			return raw_bytes.decode(encoding)
		except UnicodeDecodeError:
			continue
	return raw_bytes.decode("utf-8", errors="replace")


def read_csv_bytes(raw_bytes: bytes) -> tuple[list[str], list[dict[str, str]]]:
	"""Read CSV bytes into (fieldnames, list_of_cleaned_dicts)."""
	text = _decode_bytes(raw_bytes).replace("\ufeff", "")
	reader = csv.DictReader(io.StringIO(text, newline=""))
	if not reader.fieldnames:
		return [], []
	fieldnames = [clean_cell(col) for col in reader.fieldnames]
	rows: list[dict[str, str]] = []
	for raw_row in reader:
		cleaned = {}
		for key, val in raw_row.items():
			if key is None:
				continue
			cleaned[clean_cell(key)] = clean_cell(val)
		rows.append(cleaned)
	return fieldnames, rows


def read_excel_file(file_path: str) -> tuple[list[str], list[dict[str, str]]]:
	"""Lazy-load openpyxl only when an Excel file is uploaded."""
	try:
		import openpyxl
	except ImportError as exc:
		raise RuntimeError(
			_("openpyxl is required to read .xlsx files. Please upload CSV/ZIP or install openpyxl.")
		) from exc

	wb = openpyxl.load_workbook(file_path, read_only=True, data_only=True)
	ws = wb.active
	all_rows = list(ws.iter_rows(values_only=True))
	wb.close()
	if not all_rows:
		return [], []
	headers = [clean_cell(h) for h in all_rows[0]]
	rows: list[dict[str, str]] = []
	for raw in all_rows[1:]:
		row_dict = {}
		for idx, h in enumerate(headers):
			if not h:
				continue
			val = raw[idx] if idx < len(raw) else ""
			if isinstance(val, (datetime, date)):
				row_dict[h] = val.strftime("%Y-%m-%d")
			else:
				row_dict[h] = clean_cell(val)
		rows.append(row_dict)
	return headers, rows


def read_tabular_file(file_path: str) -> tuple[list[str], list[dict[str, str]]]:
	"""Read a CSV or Excel file from disk."""
	ext = os.path.splitext(file_path)[1].lower()
	if ext == ".csv":
		with open(file_path, "rb") as fh:
			return read_csv_bytes(fh.read())
	if ext in (".xlsx", ".xlsm"):
		return read_excel_file(file_path)
	raise ValueError(_("Unsupported file format: {0}. Please upload .zip, .csv, or .xlsx.").format(ext))


def _find_zip_member(
	names: list[str],
	include_keywords: tuple[str, ...],
	exclude_keywords: tuple[str, ...] = (),
) -> str | None:
	for name in names:
		base = os.path.basename(name).lower()
		if not base.endswith(".csv"):
			continue
		if any(k in base for k in include_keywords) and not any(ex in base for ex in exclude_keywords):
			return name
	return None


def load_daftra_source(
	stage: str,
	main_file_path: str,
	child_file_path: str | None = None,
) -> tuple[list[str], list[dict[str, str]], list[str], list[dict[str, str]]]:
	"""Load main and optional child CSV/Excel data from a Daftra .zip archive or separate files."""
	if not main_file_path or not os.path.exists(main_file_path):
		raise FileNotFoundError(_("File not found for {0}: {1}").format(stage, main_file_path))

	ext = os.path.splitext(main_file_path)[1].lower()
	if ext == ".zip":
		with zipfile.ZipFile(main_file_path, "r") as zf:
			members = [n for n in zf.namelist() if not n.endswith("/") and n.lower().endswith(".csv")]
			if stage == "Item":
				main_member = _find_zip_member(members, ("product", "item")) or (members[0] if members else None)
				child_member = None
			elif stage == "Customer":
				main_member = _find_zip_member(members, ("client",), exclude_keywords=("contact",))
				child_member = _find_zip_member(members, ("contact",))
			elif stage == "Supplier":
				main_member = _find_zip_member(members, ("supplier",), exclude_keywords=("contact",))
				child_member = _find_zip_member(members, ("contact",))
			elif stage in ("Purchase Invoice", "Purchase Return"):
				main_member = _find_zip_member(
					members, ("purchase_order", "purchase", "debit_note", "refund"), exclude_keywords=("item",)
				)
				child_member = _find_zip_member(members, ("purchase_order_item", "item"))
			elif stage in ("Sales Invoice", "Sales Return"):
				main_member = _find_zip_member(
					members, ("invoice", "credit_note", "refund"), exclude_keywords=("item",)
				)
				child_member = _find_zip_member(members, ("invoice_item", "credit_note_item", "item"))
			else:
				raise ValueError(_("Unsupported stage: {0}").format(stage))

			if not main_member:
				raise ValueError(_("Could not find main CSV inside ZIP for {0}.").format(stage))

			main_headers, main_rows = read_csv_bytes(zf.read(main_member))
			if child_member:
				child_headers, child_rows = read_csv_bytes(zf.read(child_member))
			else:
				child_headers, child_rows = [], []
			return main_headers, main_rows, child_headers, child_rows

	main_headers, main_rows = read_tabular_file(main_file_path)
	if child_file_path:
		if not os.path.exists(child_file_path):
			raise FileNotFoundError(_("Child file not found for {0}: {1}").format(stage, child_file_path))
		child_headers, child_rows = read_tabular_file(child_file_path)
	else:
		child_headers, child_rows = [], []
	return main_headers, main_rows, child_headers, child_rows


def detect_row_tax_inclusive(
	unit_price: float,
	quantity: float,
	subtotal_without_tax: float,
	subtotal: float,
	tax_mode: str,
) -> bool:
	"""Determine whether a Daftra item row's unit_price is tax-inclusive or tax-exclusive."""
	if tax_mode == "Tax Inclusive":
		return True
	if tax_mode == "Tax Exclusive":
		return False
	gross_calc = flt(abs(unit_price) * abs(quantity), 4)
	diff_inclusive = abs(gross_calc - abs(subtotal))
	diff_exclusive = abs(gross_calc - abs(subtotal_without_tax))
	return diff_inclusive < diff_exclusive


def is_return_invoice_row(inv_row: dict[str, str], rel_items: list[dict[str, str]], force_return: bool = False) -> bool:
	"""Detect if a Daftra invoice is a Return (Credit/Debit Note)."""
	if force_return:
		return True
	if flt(inv_row.get("SummaryTotal"), 4) < 0:
		return True
	inv_type = (inv_row.get("Type") or inv_row.get("InvoiceType") or "").lower()
	if any(k in inv_type for k in ("return", "credit", "debit", "refund", "مرتجع")):
		return True
	return any(flt(it.get("quantity"), 4) < 0 for it in rel_items)


def _resolve_invoice_columns(stage: str, main_headers: list[str]) -> tuple[str, str]:
	header_set = set(main_headers)
	if stage in ("Sales Invoice", "Sales Return"):
		no_col = "InvoiceNo" if "InvoiceNo" in header_set else ("CreditNoteNo" if "CreditNoteNo" in header_set else "InvoiceNo")
		party_col = "ClientBusinessName"
	elif stage in ("Purchase Invoice", "Purchase Return"):
		no_col = "PurchaseOrderNo" if "PurchaseOrderNo" in header_set else ("DebitNoteNo" if "DebitNoteNo" in header_set else "PurchaseOrderNo")
		party_col = "SupplierBusinessName"
	else:
		raise ValueError(_("Unsupported stage: {0}").format(stage))
	return no_col, party_col


def validate_stage_data(
	stage: str,
	main_file_path: str,
	child_file_path: str | None = None,
	tax_mode: str = "Both (Auto-detect per row)",
	force_return: bool = False,
) -> dict:
	"""Validate a Daftra stage dataset without mutating the database."""
	logs: list[dict] = []
	main_headers, main_rows, child_headers, child_rows = load_daftra_source(
		stage, main_file_path, child_file_path
	)

	if stage == "Item":
		required = {"ProductCode", "Name"}
		missing = required - set(main_headers)
		if missing:
			logs.append({
				"stage": _(stage),
				"row_number": 0,
				"reference_no": "",
				"severity": "Error",
				"message": _("Missing required columns in Products file: {0}").format(", ".join(sorted(missing))),
			})
			return {"total_records": len(main_rows), "valid_records": 0, "logs": logs}

		valid = 0
		seen_codes = set()
		for idx, row in enumerate(main_rows, start=2):
			code = row.get("ProductCode") or row.get("Name")
			name = row.get("Name") or code
			if not code or not name:
				logs.append({
					"stage": _(stage),
					"row_number": idx,
					"reference_no": code or "",
					"severity": "Error",
					"message": _("Product code or product name is empty."),
				})
				continue
			if code in seen_codes:
				logs.append({
					"stage": _(stage),
					"row_number": idx,
					"reference_no": code,
					"severity": "Warning",
					"message": _("Duplicate product code '{0}' in file.").format(code),
				})
			seen_codes.add(code)
			valid += 1
		return {"total_records": len(main_rows), "valid_records": valid, "logs": logs}

	if stage in ("Customer", "Supplier"):
		required = {"BusinessName"}
		missing = required - set(main_headers)
		if missing:
			logs.append({
				"stage": _(stage),
				"row_number": 0,
				"reference_no": "",
				"severity": "Error",
				"message": _("Missing required columns: {0}").format(", ".join(sorted(missing))),
			})
			return {"total_records": len(main_rows), "valid_records": 0, "logs": logs}

		num_col = "ClientNumber" if stage == "Customer" else "SupplierNumber"
		valid = 0
		for idx, row in enumerate(main_rows, start=2):
			name = row.get("BusinessName") or f"{row.get('FirstName', '')} {row.get('LastName', '')}".strip()
			ref = row.get(num_col) or name
			if not name:
				logs.append({
					"stage": _(stage),
					"row_number": idx,
					"reference_no": ref,
					"severity": "Error",
					"message": _("Business name is empty for record {0}.").format(ref or idx),
				})
				continue
			valid += 1
		return {"total_records": len(main_rows), "valid_records": valid, "logs": logs}

	no_col, party_col = _resolve_invoice_columns(stage, main_headers)
	req_main = {no_col, party_col, "Date", "CurrencyCode", "SummaryTotal"}
	req_child = {"no", "item", "unit_price", "quantity", "subtotal", "subtotal_without_tax", "tax1_value", "tax1_amount"}

	missing_main = req_main - set(main_headers)
	missing_child = req_child - set(child_headers)
	if missing_main:
		logs.append({
			"stage": _(stage),
			"row_number": 0,
			"reference_no": "",
			"severity": "Error",
			"message": _("Missing required columns in main invoices file: {0}").format(", ".join(sorted(missing_main))),
		})
	if missing_child:
		logs.append({
			"stage": _(stage),
			"row_number": 0,
			"reference_no": "",
			"severity": "Error",
			"message": _("Missing required columns in invoice items file: {0}").format(", ".join(sorted(missing_child))),
		})
	if missing_main or missing_child:
		return {"total_records": len(main_rows), "valid_records": 0, "logs": logs}

	items_by_no: dict[str, list[dict[str, str]]] = {}
	for item_row in child_rows:
		items_by_no.setdefault(item_row.get("no", ""), []).append(item_row)

	header_nos = set()
	valid = 0
	for idx, inv_row in enumerate(main_rows, start=2):
		inv_no = inv_row.get(no_col, "")
		party_name = inv_row.get(party_col, "")
		parsed_date = parse_date_str(inv_row.get("Date"))
		currency = inv_row.get("CurrencyCode", "")
		summary_total = flt(inv_row.get("SummaryTotal"), 2)
		summary_discount = flt(inv_row.get("SummaryDiscount"), 2)

		missing_reasons = []
		if not inv_no:
			missing_reasons.append(_("Invoice number is empty"))
		if not party_name:
			missing_reasons.append(_("Customer/Supplier name is empty"))
		if not parsed_date:
			missing_reasons.append(_("Invalid or empty date ({0})").format(inv_row.get("Date") or ""))
		if not currency:
			missing_reasons.append(_("Currency code is empty"))

		if missing_reasons:
			logs.append({
				"stage": _(stage),
				"row_number": idx,
				"reference_no": inv_no,
				"severity": "Error",
				"message": _("Invoice {0}: {1}.").format(inv_no or idx, ", ".join(missing_reasons)),
			})
			continue

		header_nos.add(inv_no)
		rel_items = items_by_no.get(inv_no, [])
		if not rel_items:
			logs.append({
				"stage": _(stage),
				"row_number": idx,
				"reference_no": inv_no,
				"severity": "Error",
				"message": _("Invoice {0} has no items in the items file.").format(inv_no),
			})
			continue

		is_ret = is_return_invoice_row(inv_row, rel_items, force_return=force_return)
		row_has_error = False
		sum_item_subtotal = 0.0

		for item_row in rel_items:
			qty = flt(item_row.get("quantity"), 4)
			sub_nt = abs(flt(item_row.get("subtotal_without_tax"), 4))
			sub = abs(flt(item_row.get("subtotal"), 4))
			t1_amt = abs(flt(item_row.get("tax1_amount"), 4))
			t2_amt = abs(flt(item_row.get("tax2_amount"), 4))
			if qty == 0 or (not is_ret and qty < 0):
				logs.append({
					"stage": _(stage),
					"row_number": idx,
					"reference_no": inv_no,
					"severity": "Error",
					"message": _("Invoice {0}, item '{1}': invalid quantity ({2}).").format(inv_no, item_row.get("item"), qty),
				})
				row_has_error = True
				break
			if abs((sub_nt + t1_amt + t2_amt) - sub) > 0.05:
				logs.append({
					"stage": _(stage),
					"row_number": idx,
					"reference_no": inv_no,
					"severity": "Error",
					"message": _("Invoice {0}, item '{1}': net amount ({2}) + tax ({3}) does not equal item subtotal ({4}).").format(
						inv_no, item_row.get("item"), sub_nt, t1_amt + t2_amt, sub
					),
				})
				row_has_error = True
				break
			sum_item_subtotal += sub

		if row_has_error:
			continue

		expected_total = flt(sum_item_subtotal - abs(summary_discount), 2)
		if abs(expected_total - abs(summary_total)) > 0.15:
			logs.append({
				"stage": _(stage),
				"row_number": idx,
				"reference_no": inv_no,
				"severity": "Error",
				"message": _("Invoice {0}: sum of items ({1}) minus discount ({2}) = {3}, which does not match Daftra total ({4}).").format(
					inv_no, round(sum_item_subtotal, 2), round(abs(summary_discount), 2), expected_total, abs(summary_total)
				),
			})
			continue

		valid += 1

	orphan_nos = sorted(set(items_by_no.keys()) - header_nos - {""})
	if orphan_nos:
		sample = ", ".join(orphan_nos[:5])
		logs.append({
			"stage": _(stage),
			"row_number": 0,
			"reference_no": sample,
			"severity": "Warning",
			"message": _("{0} invoice number(s) exist in the items file without a valid header invoice (e.g. {1}).").format(
				len(orphan_nos), sample
			),
		})

	return {"total_records": len(main_rows), "valid_records": valid, "logs": logs}
