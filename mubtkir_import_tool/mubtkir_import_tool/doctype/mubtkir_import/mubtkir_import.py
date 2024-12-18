# Copyright (c) 2024, Nextash and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
import pandas as pd
import os
import odf
from frappe.utils.file_manager import  get_file_path 

class MubtkirImport(Document):
	def validate(self):
		# frappe.msgprint(self.doctype_1)
		# frappe.msgprint(f"{self.main_file}")
		# frappe.msgprint(f"{self.child_table}")
		sales_order_file = get_file_path(self.main_file)
		frappe.msgprint(f"{sales_order_file}")
		items_file = get_file_path(self.child_table)
		frappe.msgprint(f"{items_file}")
		if os.path.exists(sales_order_file):
			frappe.msgprint(f"Sales order file exists: {sales_order_file}")
		else:
			frappe.msgprint(f"Sales order file not found: {sales_order_file}")
		if os.path.exists(items_file):
			frappe.msgprint(f"Items file exists: {items_file}")
		else:
			frappe.msgprint(f"Items file not found: {items_file}")
		# sales_order_file = self.main_file  
		# items_file = self.child_table  

		# try:
		sales_order_data = pd.read_excel(sales_order_file)
		items_data = pd.read_excel(items_file)
		# except Exception as e:
		# 	frappe.log_error(f"Failed to load Excel files: {str(e)}", "Sales Order Import Error")
		# 	return

		for _, so_row in sales_order_data.iterrows():
			# try:
				invoice_no = so_row['InvoiceNo']
				customer_name = so_row['ClientBusinessName']

				if not frappe.db.exists("Customer", customer_name):
					customer = frappe.new_doc("Customer")
					customer.customer_name = customer_name
					customer.customer_type = "Company"  
					customer.customer_group = "Commercial" 
					customer.territory = "Saudi Arabia" 
					customer.insert()
					frappe.db.commit()

				sales_order = frappe.new_doc(self.doctype_1)
				sales_order.transaction_date = so_row['Date']
				sales_order.customer = customer_name
				sales_order.currency = so_row['CurrencyCode']
				sales_order.payment_status = so_row.get('PaymentStatus', 'Unpaid')  

				sales_order.city = so_row.get('ClientCity')
				sales_order.state = so_row.get('ClientState')
				sales_order.country = so_row.get('ClientCountryCode')

				related_items = items_data[items_data['InvoiceNo'] == invoice_no]

				for _, item_row in related_items.iterrows():
					item_code = item_row['item']

					if not frappe.db.exists("Item", item_code):
						frappe.log_error(f"Item '{item_code}' not found for Invoice {invoice_no}", "Sales Order Import Error")
						continue

					sales_order.append("items", {
						"item_code": item_code,
						"description": item_row['description'],
						"rate": item_row['unit_price'],
						"qty": item_row['quantity'],
						"amount": item_row['subtotal']
					})
				frappe.msgprint(sales_order.name)
				sales_order.insert()
				# sales_order.submit()
				frappe.db.commit()
				frappe.log_error(f"Sales Order {invoice_no} imported successfully.", "Sales Order Import Success")

			# except Exception as e:
			# 	frappe.log_error(f"Error processing Invoice {so_row['InvoiceNo']}: {str(e)}", "Sales Order Import Error")