# Copyright (c) 2026, Nextash and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import flt

from .daftra_parser import (
	_resolve_invoice_columns,
	detect_row_tax_inclusive,
	is_return_invoice_row,
	load_daftra_source,
	parse_date_str,
)


def _get_default_company(company: str | None = None) -> str:
	if company:
		return company
	return (
		frappe.defaults.get_user_default("Company")
		or frappe.db.get_single_value("Global Defaults", "default_company")
		or frappe.db.get_value("Company", {}, "name")
	)


def _get_country_name(country_code: str) -> str | None:
	code = (country_code or "").strip().lower()
	if not code:
		return None
	return frappe.db.get_value("Country", {"code": code}, "name")


def _get_tax_template_rows(template_doctype: str, template_name: str) -> list[dict]:
	if not template_name:
		return []
	child_doctype = (
		"Sales Taxes and Charges"
		if template_doctype == "Sales Taxes and Charges Template"
		else "Purchase Taxes and Charges"
	)
	return frappe.get_all(
		child_doctype,
		filters={"parent": template_name},
		fields=["charge_type", "account_head", "description", "rate"],
		order_by="idx asc",
	)


def import_items(main_file_path: str, child_file_path: str | None = None, skip_existing: bool = True, item_group: str | None = None, progress_cb=None) -> dict:
	"""Import Daftra Products CSV/ZIP into ERPNext Item DocType."""
	_, rows, _, _ = load_daftra_source("Item", main_file_path, child_file_path)
	existing_codes = set(frappe.get_all("Item", pluck="name"))
	default_group = item_group or frappe.db.get_single_value("Stock Settings", "item_group") or "All Item Groups"
	default_uom = frappe.db.get_single_value("Stock Settings", "stock_uom") or "Nos"

	imported = 0
	skipped = 0
	failed = 0
	logs: list[dict] = []
	total = len(rows)

	for idx, row in enumerate(rows, start=1):
		code = (row.get("ProductCode") or row.get("Name") or "")[:140]
		name = (row.get("Name") or code)[:140]
		if not code:
			failed += 1
			logs.append({
				"stage": _("Item"),
				"row_number": idx + 1,
				"reference_no": "",
				"severity": "Error",
				"message": _("Product code and name are both empty."),
			})
			continue

		if code in existing_codes and skip_existing:
			skipped += 1
			if progress_cb and idx % 25 == 0:
				progress_cb(idx, total)
			continue

		sp = f"imp_item_{idx}"
		frappe.db.savepoint(sp)
		try:
			if code in existing_codes:
				doc = frappe.get_doc("Item", code)
			else:
				doc = frappe.new_doc("Item")
				doc.item_code = code
				doc.item_group = default_group
				doc.stock_uom = default_uom

			doc.item_name = name
			doc.description = row.get("Description") or name
			doc.standard_rate = flt(row.get("UnitPrice"), 4)
			doc.valuation_rate = (
				flt(row.get("AverageCost"), 4)
				or flt(row.get("BuyPrice"), 4)
				or flt(row.get("UnitPrice"), 4)
				or 0.01
			)
			doc.is_stock_item = 1 if row.get("TrackStock") in ("1", "True", "true", "") else 0

			barcode = (row.get("Barcode") or "").strip()
			if barcode and not any(b.barcode == barcode for b in (doc.barcodes or [])):
				doc.append("barcodes", {"barcode": barcode})

			doc.save(ignore_permissions=True)
			existing_codes.add(code)
			imported += 1
		except Exception as exc:
			frappe.db.rollback(save_point=sp)
			failed += 1
			logs.append({
				"stage": _("Item"),
				"row_number": idx + 1,
				"reference_no": code,
				"severity": "Error",
				"message": str(exc)[:300],
			})

		if idx % 50 == 0:
			frappe.db.commit()
			if progress_cb:
				progress_cb(idx, total)

	frappe.db.commit()
	return {"total": total, "imported": imported, "skipped": skipped, "failed": failed, "logs": logs}


def import_customers(main_file_path: str, child_file_path: str | None = None, skip_existing: bool = True, customer_group: str | None = None, progress_cb=None) -> dict:
	"""Import Daftra Clients (+ Client_contacts) into ERPNext Customer DocType."""
	_, rows, _, contact_rows = load_daftra_source("Customer", main_file_path, child_file_path)
	contacts_by_no = {c.get("ClientNumber", ""): c for c in contact_rows if c.get("ClientNumber")}
	existing_names = set(frappe.get_all("Customer", pluck="name"))
	default_group = customer_group or frappe.db.get_single_value("Selling Settings", "customer_group") or "All Customer Groups"
	default_territory = frappe.db.get_single_value("Selling Settings", "territory") or "All Territories"

	imported = 0
	skipped = 0
	failed = 0
	logs: list[dict] = []
	total = len(rows)

	for idx, row in enumerate(rows, start=1):
		cust_name = (row.get("BusinessName") or f"{row.get('FirstName', '')} {row.get('LastName', '')}".strip())[:140]
		ref = row.get("ClientNumber") or cust_name
		if not cust_name:
			failed += 1
			logs.append({
				"stage": _("Customer"),
				"row_number": idx + 1,
				"reference_no": ref,
				"severity": "Error",
				"message": _("Customer name is empty."),
			})
			continue

		if cust_name in existing_names and skip_existing:
			skipped += 1
			continue

		sp = f"imp_cust_{idx}"
		frappe.db.savepoint(sp)
		try:
			if cust_name in existing_names:
				doc = frappe.get_doc("Customer", cust_name)
			else:
				doc = frappe.new_doc("Customer")
				doc.customer_name = cust_name
				doc.customer_type = "Company" if row.get("BusinessName") else "Individual"
				doc.customer_group = default_group
				doc.territory = default_territory

			tax_id = row.get("BusinessNumber1") or ""
			if tax_id:
				doc.tax_id = tax_id

			contact = contacts_by_no.get(row.get("ClientNumber", ""), {})
			email = row.get("Email") or contact.get("Email") or ""
			mobile = row.get("Phone1") or row.get("Phone2") or contact.get("mobile") or contact.get("HomePhone") or ""
			if email:
				doc.email_id = email
			if mobile:
				doc.mobile_no = mobile

			doc.save(ignore_permissions=True)
			existing_names.add(doc.name)
			imported += 1
		except Exception as exc:
			frappe.db.rollback(save_point=sp)
			failed += 1
			logs.append({
				"stage": _("Customer"),
				"row_number": idx + 1,
				"reference_no": ref,
				"severity": "Error",
				"message": str(exc)[:300],
			})

		if idx % 50 == 0:
			frappe.db.commit()
			if progress_cb:
				progress_cb(idx, total)

	frappe.db.commit()
	return {"total": total, "imported": imported, "skipped": skipped, "failed": failed, "logs": logs}


def import_suppliers(main_file_path: str, child_file_path: str | None = None, skip_existing: bool = True, supplier_group: str | None = None, progress_cb=None) -> dict:
	"""Import Daftra Suppliers (+ Supplier_contacts) into ERPNext Supplier DocType."""
	_, rows, _, contact_rows = load_daftra_source("Supplier", main_file_path, child_file_path)
	contacts_by_no = {c.get("supplier_number", ""): c for c in contact_rows if c.get("supplier_number")}
	existing_names = set(frappe.get_all("Supplier", pluck="name"))
	default_group = supplier_group or frappe.db.get_single_value("Buying Settings", "supplier_group") or "All Supplier Groups"

	imported = 0
	skipped = 0
	failed = 0
	logs: list[dict] = []
	total = len(rows)

	for idx, row in enumerate(rows, start=1):
		sup_name = (row.get("BusinessName") or f"{row.get('FirstName', '')} {row.get('LastName', '')}".strip())[:140]
		ref = row.get("SupplierNumber") or sup_name
		if not sup_name:
			failed += 1
			logs.append({
				"stage": _("Supplier"),
				"row_number": idx + 1,
				"reference_no": ref,
				"severity": "Error",
				"message": _("Supplier name is empty."),
			})
			continue

		if sup_name in existing_names and skip_existing:
			skipped += 1
			continue

		sp = f"imp_sup_{idx}"
		frappe.db.savepoint(sp)
		try:
			if sup_name in existing_names:
				doc = frappe.get_doc("Supplier", sup_name)
			else:
				doc = frappe.new_doc("Supplier")
				doc.supplier_name = sup_name
				doc.supplier_type = "Company" if row.get("BusinessName") else "Individual"
				doc.supplier_group = default_group

			country = _get_country_name(row.get("CountryCode", ""))
			if country:
				doc.country = country
			if row.get("bn1"):
				doc.tax_id = row.get("bn1")

			contact = contacts_by_no.get(row.get("SupplierNumber", ""), {})
			email = row.get("Email") or contact.get("email") or ""
			mobile = row.get("Phone1") or row.get("Phone2") or contact.get("mobile") or contact.get("home_phone") or ""
			if email and doc.meta.has_field("email_id"):
				doc.email_id = email
			if mobile and doc.meta.has_field("mobile_no"):
				doc.mobile_no = mobile

			doc.save(ignore_permissions=True)
			existing_names.add(doc.name)
			imported += 1
		except Exception as exc:
			frappe.db.rollback(save_point=sp)
			failed += 1
			logs.append({
				"stage": _("Supplier"),
				"row_number": idx + 1,
				"reference_no": ref,
				"severity": "Error",
				"message": str(exc)[:300],
			})

		if idx % 50 == 0:
			frappe.db.commit()
			if progress_cb:
				progress_cb(idx, total)

	frappe.db.commit()
	return {"total": total, "imported": imported, "skipped": skipped, "failed": failed, "logs": logs}


def _build_item_lookup() -> dict[str, str]:
	"""Map both item_code and item_name to Item.name for fast O(1) lookup."""
	lookup: dict[str, str] = {}
	for row in frappe.get_all("Item", fields=["name", "item_name"]):
		lookup[row.name] = row.name
		if row.item_name:
			lookup[row.item_name.strip()] = row.name
	return lookup


def _ensure_party(
	party_type: str,
	party_name: str,
	existing_parties: set[str],
	country_code: str = "",
	party_group: str | None = None,
) -> str:
	if party_name in existing_parties:
		return party_name
	doc = frappe.new_doc(party_type)
	if party_type == "Customer":
		doc.customer_name = party_name[:140]
		doc.customer_type = "Company"
		doc.customer_group = party_group or frappe.db.get_single_value("Selling Settings", "customer_group") or "All Customer Groups"
		doc.territory = frappe.db.get_single_value("Selling Settings", "territory") or "All Territories"
	else:
		doc.supplier_name = party_name[:140]
		doc.supplier_type = "Company"
		doc.supplier_group = party_group or frappe.db.get_single_value("Buying Settings", "supplier_group") or "All Supplier Groups"
		country = _get_country_name(country_code)
		if country:
			doc.country = country
	doc.insert(ignore_permissions=True)
	existing_parties.add(doc.name)
	return doc.name


def import_invoices(
	stage: str,
	main_file_path: str,
	child_file_path: str | None = None,
	company: str | None = None,
	tax_mode: str = "Both (Auto-detect per row)",
	tax_template: str | None = None,
	submit_invoices: bool = True,
	update_stock: bool = False,
	skip_existing: bool = True,
	force_return: bool = False,
	default_item_group: str | None = None,
	default_customer_group: str | None = None,
	default_supplier_group: str | None = None,
	progress_cb=None,
) -> dict:
	"""
	Unified importer for Daftra Sales Invoices, Purchase Invoices, and Return Invoices (Credit/Debit Notes).
	Guarantees 100% tax & grand_total accuracy against Daftra's SummaryTotal.
	"""
	if stage in ("Sales Invoice", "Sales Return"):
		target_doctype = "Sales Invoice"
		party_type = "Customer"
		party_field = "customer"
		country_col = "ClientCountryCode"
		ref_field = "po_no"
		template_doctype = "Sales Taxes and Charges Template"
	elif stage in ("Purchase Invoice", "Purchase Return"):
		target_doctype = "Purchase Invoice"
		party_type = "Supplier"
		party_field = "supplier"
		country_col = "SupplierCountryCode"
		ref_field = "bill_no"
		template_doctype = "Purchase Taxes and Charges Template"
	else:
		raise ValueError(_("Invalid invoice stage: {0}").format(stage))

	company = _get_default_company(company)
	main_headers, main_rows, _, child_rows = load_daftra_source(stage, main_file_path, child_file_path)
	no_col, party_col = _resolve_invoice_columns(stage, main_headers)

	items_by_no: dict[str, list[dict[str, str]]] = {}
	for item_row in child_rows:
		items_by_no.setdefault(item_row.get("no", ""), []).append(item_row)

	has_daftra_col = frappe.db.has_column(target_doctype, "custom_daftra_no")
	existing_map: dict[str, str] = {}
	if has_daftra_col:
		for r in frappe.get_all(
			target_doctype,
			filters={"custom_daftra_no": ["is", "set"], "docstatus": ["<", 2]},
			fields=["name", "custom_daftra_no"],
		):
			existing_map[r.custom_daftra_no] = r.name
	else:
		for r in frappe.get_all(
			target_doctype,
			filters={ref_field: ["is", "set"], "docstatus": ["<", 2]},
			fields=["name", ref_field],
		):
			existing_map[r.get(ref_field)] = r.name

	existing_parties = set(frappe.get_all(party_type, pluck="name"))
	item_lookup = _build_item_lookup()
	default_item_group = default_item_group or frappe.db.get_single_value("Stock Settings", "item_group") or "All Item Groups"
	party_group = default_customer_group if party_type == "Customer" else default_supplier_group
	default_uom = frappe.db.get_single_value("Stock Settings", "stock_uom") or "Nos"
	template_rows = _get_tax_template_rows(template_doctype, tax_template or "")

	imported = 0
	skipped = 0
	failed = 0
	logs: list[dict] = []
	total = len(main_rows)

	for idx, inv_row in enumerate(main_rows, start=1):
		inv_no = inv_row.get(no_col, "")
		if skip_existing and inv_no in existing_map:
			skipped += 1
			if progress_cb and idx % 25 == 0:
				progress_cb(idx, total)
			continue

		party_name = inv_row.get(party_col, "")
		posting_date = parse_date_str(inv_row.get("Date"))
		currency = inv_row.get("CurrencyCode", "")
		summary_total = flt(inv_row.get("SummaryTotal"), 2)
		summary_discount = flt(inv_row.get("SummaryDiscount"), 2)
		rel_items = items_by_no.get(inv_no, [])

		if not inv_no or not party_name or not posting_date or not currency or not rel_items:
			failed += 1
			logs.append({
				"stage": _(stage),
				"row_number": idx + 1,
				"reference_no": inv_no,
				"severity": "Error",
				"message": _("Invoice {0}: missing required fields (customer/supplier, date, currency, or items).").format(inv_no or idx),
			})
			continue

		is_ret = is_return_invoice_row(inv_row, rel_items, force_return=force_return)
		expected_grand = -abs(summary_total) if is_ret else summary_total

		sp = f"imp_inv_{idx}"
		frappe.db.savepoint(sp)
		try:
			party = _ensure_party(party_type, party_name, existing_parties, inv_row.get(country_col, ""), party_group=party_group)

			doc = frappe.new_doc(target_doctype)
			doc.company = company
			doc.set(party_field, party)
			doc.set_posting_time = 1
			doc.posting_date = posting_date
			doc.due_date = posting_date
			doc.currency = currency
			doc.update_stock = 1 if update_stock else 0
			doc.set(ref_field, inv_no)
			if has_daftra_col:
				doc.custom_daftra_no = inv_no

			if is_ret:
				doc.is_return = 1
				orig_ref = (
					inv_row.get("ReturnAgainst")
					or inv_row.get("ParentInvoiceNo")
					or inv_row.get("OriginalInvoiceNo")
					or ""
				)
				if orig_ref and orig_ref in existing_map:
					doc.return_against = existing_map[orig_ref]

			row_tax_rates: set[float] = set()
			total_daftra_tax = 0.0

			for item_row in rel_items:
				qty = abs(flt(item_row.get("quantity"), 6))
				unit_price = abs(flt(item_row.get("unit_price"), 6))
				sub_nt = abs(flt(item_row.get("subtotal_without_tax"), 6))
				sub = abs(flt(item_row.get("subtotal"), 6))
				t1_val = flt(item_row.get("tax1_value"), 4)
				t2_val = flt(item_row.get("tax2_value"), 4)
				t1_amt = abs(flt(item_row.get("tax1_amount"), 6))
				t2_amt = abs(flt(item_row.get("tax2_amount"), 6))

				_is_inclusive = detect_row_tax_inclusive(unit_price, qty, sub_nt, sub, tax_mode)
				net_rate = flt(sub_nt / qty, 9) if qty else 0.0

				item_label = (item_row.get("item") or "").strip()
				item_code = item_lookup.get(item_label)
				if not item_code:
					new_code = item_label[:140]
					if not frappe.db.exists("Item", new_code):
						new_item = frappe.new_doc("Item")
						new_item.item_code = new_code
						new_item.item_name = new_code
						new_item.item_group = default_item_group
						new_item.stock_uom = default_uom
						new_item.standard_rate = flt(net_rate, 4)
						new_item.valuation_rate = flt(net_rate, 4) or 0.01
						new_item.description = item_row.get("description") or new_code
						new_item.insert(ignore_permissions=True)
					item_code = new_code
					item_lookup[item_label] = item_code
					item_lookup[new_code] = item_code

				row_tax_rates.add(flt(t1_val + t2_val, 4))
				total_daftra_tax += (t1_amt + t2_amt)

				item_dict = {
					"item_code": item_code,
					"description": item_row.get("description") or item_label,
					"qty": -qty if is_ret else qty,
					"rate": net_rate,
				}
				if target_doctype == "Sales Invoice" and update_stock:
					item_dict["allow_zero_valuation_rate"] = 1
				doc.append("items", item_dict)

			total_daftra_tax = flt(total_daftra_tax, 2)
			if total_daftra_tax > 0:
				if (
					len(row_tax_rates) == 1
					and len(template_rows) == 1
					and abs(flt(template_rows[0]["rate"], 4) - next(iter(row_tax_rates))) < 0.01
				):
					doc.taxes_and_charges = tax_template
					doc.append("taxes", {
						"charge_type": "On Net Total",
						"account_head": template_rows[0]["account_head"],
						"description": template_rows[0]["description"] or "VAT",
						"rate": template_rows[0]["rate"],
						"included_in_print_rate": 0,
					})
				else:
					if not template_rows:
						frappe.throw(_("Please select a {0} to provide the tax account.").format(template_doctype))
					doc.append("taxes", {
						"charge_type": "Actual",
						"account_head": template_rows[0]["account_head"],
						"description": template_rows[0]["description"] or "VAT",
						"tax_amount": -total_daftra_tax if is_ret else total_daftra_tax,
						"included_in_print_rate": 0,
					})

			if summary_discount != 0:
				disc = abs(summary_discount)
				doc.apply_discount_on = "Grand Total"
				doc.discount_amount = -disc if is_ret else disc

			doc.insert(ignore_permissions=True)

			if abs(flt(doc.grand_total, 2) - expected_grand) > 0.05:
				frappe.throw(
					_("Invoice {0}: total mismatch (ERPNext={1}, Daftra={2}).").format(
						inv_no, flt(doc.grand_total, 2), expected_grand
					)
				)

			if submit_invoices:
				doc.submit()

			existing_map[inv_no] = doc.name
			imported += 1
		except Exception as exc:
			frappe.db.rollback(save_point=sp)
			failed += 1
			logs.append({
				"stage": _(stage),
				"row_number": idx + 1,
				"reference_no": inv_no,
				"severity": "Error",
				"message": str(exc)[:300],
			})

		if idx % 25 == 0:
			frappe.db.commit()
			if progress_cb:
				progress_cb(idx, total)

	frappe.db.commit()
	return {"total": total, "imported": imported, "skipped": skipped, "failed": failed, "logs": logs}
