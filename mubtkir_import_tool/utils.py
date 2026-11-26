# Copyright (c) 2026, Nextash and contributors
# For license information, please see license.txt

import frappe
from frappe.utils import flt


def clamp_negative_incoming_rate(doc, method=None):
	"""Prevent ERPNext negative incoming_rate validation errors during historical bulk imports."""
	if not getattr(frappe.flags, "in_import", False):
		return
	for item in doc.get("items") or []:
		if flt(item.get("incoming_rate")) < 0:
			item.incoming_rate = 0
