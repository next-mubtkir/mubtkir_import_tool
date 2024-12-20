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
        sales_order_file = get_file_path(self.import_file)
        frappe.msgprint(f"{sales_order_file}")
        items_file = get_file_path(self.child_table)
        frappe.msgprint(f"{items_file}")
        
        # Check if sales order file exists
        if os.path.exists(sales_order_file):
            frappe.msgprint(f"Sales order file exists: {sales_order_file}")
        else:
            frappe.msgprint(f"Sales order file not found: {sales_order_file}")
        try:
            sales_order_data = pd.read_excel(sales_order_file)
            items_data = pd.read_excel(items_file)
        except Exception as e:
            frappe.log_error(f"Failed to load Excel files: {str(e)}", "Sales Order Import Error")
            return
        
        # Show columns in the loaded files
        frappe.msgprint(f"Columns in sales order file: {list(sales_order_data.columns)}")
        frappe.msgprint(f"Columns in items file: {list(items_data.columns)}")
        
        for _, so_row in sales_order_data.iterrows():
            try:
                invoice_no = so_row['InvoiceNo']
                customer_name = so_row['ClientBusinessName']

                # Check if customer exists, if not create a new one
                if not frappe.db.exists("Customer", customer_name):
                    customer = frappe.new_doc("Customer")
                    customer.customer_name = customer_name
                    customer.customer_type = "Company"
                    customer.customer_group = "Commercial"
                    customer.territory = "Saudi Arabia"
                    customer.insert()
                    frappe.db.commit()
                else:
                    # If customer exists, fetch the existing customer
                    customer = frappe.get_doc("Customer", customer_name)

                # Create Sales Order
                doc = frappe.new_doc(self.doctype_type)
                doc.transaction_date = so_row['Date']
                doc.customer = customer_name
                doc.delivery_date = datetime.today().date()  
                doc.currency = so_row['CurrencyCode']
                doc.total=so_row['SummaryTotal']
                # doc.city = so_row.get('ClientCity')
                # doc.state = so_row.get('ClientState')
                # doc.country = so_row.get('ClientCountryCode')

                # Fetch related items based on invoice number
                related_items = items_data[items_data['no'] == invoice_no]

                for _, item_row in related_items.iterrows():
                    item_code = item_row['item']
                    item_price = item_row['unit_price']
                    frappe.msgprint(f"{item_price}")
                    frappe.msgprint(f"{item_code}")
                    if not frappe.db.exists("Item", item_code):
                        item = frappe.new_doc("Item")
                        item.item_code = item_code
                        item.item_group = "كل مجموعات الأصناف" 
                        item.insert()
                        frappe.db.commit()
                        ammout=  item_row['unit_price']* item_row['quantity']
                    doc.append("items", {
                        "item_code": item_code,
                        "description": item_row['description'],
                        "rate": item_row['unit_price'], 
                        "qty": item_row['quantity'],
                        "amount": flt(ammout)  
                    })
                # frappe.msgprint(f"Sales Order created: {doc.name}")
                doc.save()
                # frappe.db.commit()
                frappe.log_error(f"Sales Order {invoice_no} imported successfully.", "Sales Order Import Success")

            except Exception as e:
                frappe.log_error(f"Error processing Invoice {so_row['InvoiceNo']}: {str(e)}", "Sales Order Import Error")

            if doc.grand_total:
                try:
                    # Calculate payment amount based on the grand total and invoice portion
                    grand_total = flt(doc.grand_total) if doc.grand_total is not None else 0
                    invoice_portion = flt(doc.invoice_portion) if doc.invoice_portion is not None else 0
                    payment_amount = grand_total * invoice_portion / 100
                    
                    # Optional: Assign the calculated payment amount to a field (if needed)
                    doc.payment_amount = payment_amount
                    doc.save()

                except Exception as calc_error:
                    frappe.log_error(f"Error calculating payment amount for Sales Order {doc.name}: {str(calc_error)}", "Payment Calculation Error")