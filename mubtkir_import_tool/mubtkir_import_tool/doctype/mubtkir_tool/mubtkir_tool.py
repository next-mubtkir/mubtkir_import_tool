# Copyright (c) 2024, Nextash and contributors
# For license information, please see license.txt

from frappe.utils import flt
import frappe
from frappe.utils.file_manager import get_file_path
import pandas as pd
import os
from datetime import datetime
from frappe.model.document import Document


class MubtkirTool(Document):
    def validate(self):
        # Get file paths for the main and child files
        sales_order_file = get_file_path(self.main_file)
        items_file = get_file_path(self.child_file)
        
        # Check if files exist
        if not os.path.exists(sales_order_file):
            frappe.throw(f"Sales order file not found: {sales_order_file}")
        if not os.path.exists(items_file):
            frappe.throw(f"Items file not found: {items_file}")
        
        
        sales_order_data = pd.read_excel(sales_order_file)
        items_data = pd.read_excel(items_file)
        
        # Validate required columns
        required_sales_order_columns = {'InvoiceNo', 'ClientBusinessName', 'Date', 'CurrencyCode', 'SummaryTotal'}
        required_items_columns = {'no', 'item', 'unit_price', 'quantity', 'description'}
        
        if not required_sales_order_columns.issubset(sales_order_data.columns):
            frappe.throw(f"Missing columns in sales order file: {required_sales_order_columns - set(sales_order_data.columns)}")
        if not required_items_columns.issubset(items_data.columns):
            frappe.throw(f"Missing columns in items file: {required_items_columns - set(items_data.columns)}")
        
        # Process each sales order
        for _, so_row in sales_order_data.iterrows():
            
            invoice_no = sanitize_data(so_row.get('InvoiceNo'))
            customer_name = sanitize_data(so_row.get('ClientBusinessName'))
            order_date = sanitize_data(so_row.get('Date'))
            currency = sanitize_data(so_row.get('CurrencyCode'))
            total_amount = flt(sanitize_data(so_row.get('SummaryTotal')), precision=2)

            # Validate mandatory fields
            if not all([invoice_no, customer_name, order_date, currency]):
                frappe.log_error(f"Missing data in Sales Order row: {so_row.to_dict()}", "Sales Order Import Error")
                continue

            # Check if customer exists, create if not
            if not frappe.db.exists("Customer", customer_name):
                customer = frappe.new_doc("Customer")
                customer.customer_name = customer_name
                customer.customer_type = "Company"
                customer.customer_group = "Commercial"
                customer.territory = "Saudi Arabia"
                customer.insert()
                frappe.db.commit()

            # Create Sales Order
            doc = frappe.new_doc(self.reference_doctype)
            order_date = so_row['Date']
            if isinstance(order_date, datetime):
                doc.transaction_date = order_date.strftime("%Y-%m-%d")
            elif isinstance(order_date, str):
                doc.transaction_date = datetime.strptime(order_date, "%m/%d/%Y").strftime("%Y-%m-%d")
            else:
                frappe.throw(f"Invalid date format for Invoice {invoice_no}: {order_date}")

            doc.customer = customer_name
            doc.delivery_date = datetime.today().date()
            doc.currency = currency
            doc.total = total_amount

            # Fetch related items
            related_items = items_data[items_data['no'] == invoice_no]

            for _, item_row in related_items.iterrows():
                item_code = sanitize_data(item_row.get('item'))
                unit_price = flt(sanitize_data(item_row.get('unit_price')), precision=2)
                quantity = flt(sanitize_data(item_row.get('quantity')), precision=2)
                description = sanitize_data(item_row.get('description'))
                amount = flt(unit_price * quantity, precision=2)

                # Check if item exists, create if not
                if not frappe.db.exists("Item", item_code):
                    item = frappe.new_doc("Item")
                    item.item_code = item_code
                    item.item_group = "All Item Groups"
                    item.insert()
                    frappe.db.commit()

                # Add item to Sales Order
                doc.append("items", {
                    "item_code": item_code,
                    "description": description,
                    "rate": unit_price,
                    "qty": quantity,
                    "amount": amount
                })

            # Save Sales Order
            doc.save()
            frappe.db.commit()

def sanitize_data(value):
    """Sanitize data to replace `nan` or invalid values with `None`."""
    if value != value:  # Checks for `nan`
        return None
    return value