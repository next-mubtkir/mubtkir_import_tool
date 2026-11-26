# Copyright (c) 2024, Nextash and Contributors
# See license.txt

import os
import zipfile

from frappe.tests.utils import FrappeTestCase

from .daftra_parser import (
	clean_cell,
	detect_row_tax_inclusive,
	parse_date_str,
	read_csv_bytes,
)


class TestMubtkirImportTool(FrappeTestCase):
	def test_clean_cell_strips_bom_and_quotes(self):
		self.assertEqual(clean_cell('\ufeff000001'), "000001")
		self.assertEqual(clean_cell('\ufeff"شركه عاصمة الدجاج"'), "شركه عاصمة الدجاج")
		self.assertEqual(clean_cell("  "), "")

	def test_parse_date_str_formats(self):
		self.assertEqual(parse_date_str("2025-12-03"), "2025-12-03")
		self.assertEqual(parse_date_str("12/03/2025"), "2025-12-03")
		self.assertIsNone(parse_date_str(" "))

	def test_read_csv_bytes_handles_bom_on_data_row(self):
		raw = (
			"\ufeffno,item,unit_price,quantity,subtotal,subtotal_without_tax,tax1_value,tax1_amount\n"
			'\ufeff000001,"دجاج",80,50,4600,4000,15.0000,600\n'
		).encode("utf-8-sig")
		headers, rows = read_csv_bytes(raw)
		self.assertEqual(headers[0], "no")
		self.assertEqual(rows[0]["no"], "000001")
		self.assertEqual(rows[0]["subtotal_without_tax"], "4000")

	def test_detect_row_tax_inclusive_modes(self):
		# Exclusive: 80 * 50 = 4000 == subtotal_without_tax
		self.assertFalse(
			detect_row_tax_inclusive(80, 50, 4000, 4600, "Both (Auto-detect per row)")
		)
		# Inclusive: 92 * 50 = 4600 == subtotal
		self.assertTrue(
			detect_row_tax_inclusive(92, 50, 4000, 4600, "Both (Auto-detect per row)")
		)
		# Explicit overrides
		self.assertTrue(detect_row_tax_inclusive(80, 50, 4000, 4600, "Tax Inclusive"))
		self.assertFalse(detect_row_tax_inclusive(92, 50, 4000, 4600, "Tax Exclusive"))
