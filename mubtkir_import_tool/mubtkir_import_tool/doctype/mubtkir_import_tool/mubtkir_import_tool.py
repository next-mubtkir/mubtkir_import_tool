# Copyright (c) 2024, Nextash and contributors
# For license information, please see license.txt

from frappe.utils import flt,strip, today
import frappe
from frappe.utils.file_manager import get_file_path
import pandas as pd
import os
from datetime import datetime
from frappe.model.document import Document


class MubtkirImportTool(Document):
    def validate(self):
        if self.main_file and self.child_file:
            if self.reference_doctype== "Sales Order":
                if self.import_data == 1:
                    sales_order_file = get_file_path(self.main_file)
                    items_file = get_file_path(self.child_file)
                    
                    if not os.path.exists(sales_order_file):
                        frappe.throw(f"Sales order file not found: {sales_order_file}")
                    if not os.path.exists(items_file):
                        frappe.throw(f"Items file not found: {items_file}")
                    
                    
                    sales_order_data = pd.read_excel(sales_order_file)
                    items_data = pd.read_excel(items_file)
                    
                    required_sales_order_columns = {'InvoiceNo', 'ClientBusinessName', 'Date', 'CurrencyCode', 'SummaryTotal','SummaryDiscount'}
                    required_items_columns = {'no', 'item', 'unit_price', 'quantity', 'description', 'tax1_name', 'tax2_name', 'tax1_value', 'tax2_value'}
                    
                    if not required_sales_order_columns.issubset(sales_order_data.columns):
                        frappe.throw(f"Missing columns in sales order file: {required_sales_order_columns - set(sales_order_data.columns)}")
                    if not required_items_columns.issubset(items_data.columns):
                        frappe.throw(f"Missing columns in items file: {required_items_columns - set(items_data.columns)}")
                    
                    for _, so_row in sales_order_data.iterrows():
                        
                        invoice_no = sanitize_data(so_row.get('InvoiceNo'))
                        customer_name = sanitize_data(so_row.get('ClientBusinessName'))
                        order_date = sanitize_data(so_row.get('Date'))
                        currency = sanitize_data(so_row.get('CurrencyCode'))
                        total_amount = flt(sanitize_data(so_row.get('SummaryTotal')), precision=2)
                        total_dicount = flt(sanitize_data(so_row.get('SummaryDiscount')), precision=2)

                        if not all([invoice_no, customer_name, order_date, currency]):
                            frappe.log_error(f"Missing data in Sales Order row: {so_row.to_dict()}", "Sales Order Import Error")
                            continue

                        if not frappe.db.exists("Customer", customer_name):
                            customer = frappe.new_doc("Customer")
                            customer.customer_name = customer_name
                            customer.customer_type = "Company"
                            customer.customer_group = "Commercial"
                            customer.territory = "Saudi Arabia"
                            customer.insert()
                            frappe.db.commit()
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
                        

                        related_items = items_data[items_data['no'] == invoice_no]

                        for _, item_row in related_items.iterrows():
                            item_code = sanitize_data(item_row.get('item'))
                            unit_price = flt(sanitize_data(item_row.get('unit_price')), precision=2)
                            quantity = flt(sanitize_data(item_row.get('quantity')), precision=2)
                            description = sanitize_data(item_row.get('description'))
                            amount = flt(unit_price * quantity, precision=2)
                            # tax_amount = flt(sanitize_data(item_row.get('tax1_amount')), precision=2) or flt(sanitize_data(item_row.get('tax2_amount')), precision=2)
                            # item_tax_template = item_row.get('tax1_name') or item_row.get('tax2_name')
                            # tax_rate = flt(sanitize_data(item_row.get('tax1_value')), precision=2) or flt(sanitize_data(item_row.get('tax2_value')), precision=2)

                            if not frappe.db.exists("Item", item_code):
                                item = frappe.new_doc("Item")
                                item.item_code = item_code
                                item.item_group = "All Item Groups"
                                item.insert()
                                frappe.db.commit()

                            doc.append("items", {
                                "item_code": item_code,
                                "description": description,
                                "rate": unit_price,
                                "qty": quantity,
                                "amount": amount
                            })
                        doc.taxes_and_charges = self.sales_taxes_and_charges_template
                        tax_rate,account_head = frappe.db.get_value('Sales Taxes and Charges',{"parent":self.sales_taxes_and_charges_template}, ['rate','account_head'],)
                        tax_amount = total_amount * (tax_rate / 100)
                        doc.append("taxes", {
                            "account_head": account_head,
                            "description": "Tax",
                            "charge_type": "On Net Total",
                            "rate": tax_rate,
                            "tax_amount":tax_amount
                        })
                        if total_dicount:
                            doc.apply_discount_on= "Grand Total"
                            doc.discount_amount = total_dicount
                        doc.save()
                        frappe.db.commit()
            if self.reference_doctype == "Sales Invoice":
                if self.import_data == 1:
                    sales_invoice_file = get_file_path(self.main_file)
                    items_file = get_file_path(self.child_file)

                    if not os.path.exists(sales_invoice_file):
                        frappe.throw(f"Sales invoice file not found: {sales_invoice_file}")
                    if not os.path.exists(items_file):
                        frappe.throw(f"Items file not found: {items_file}")

                    sales_invoice_data = pd.read_excel(sales_invoice_file)
                    items_data = pd.read_excel(items_file)

                    required_sales_invoice_columns = {'InvoiceNo', 'ClientBusinessName', 'Date', 'CurrencyCode', 'SummaryTotal','SummaryDiscount'}
                    required_items_columns = {'no', 'item', 'unit_price', 'quantity', 'description', 'tax1_name', 'tax2_name', 'tax1_value', 'tax2_value'}

                    if not required_sales_invoice_columns.issubset(sales_invoice_data.columns):
                        frappe.throw(f"Missing columns in sales invoice file: {required_sales_invoice_columns - set(sales_invoice_data.columns)}")
                    if not required_items_columns.issubset(items_data.columns):
                        frappe.throw(f"Missing columns in items file: {required_items_columns - set(items_data.columns)}")

                    for _, so_row in sales_invoice_data.iterrows():

                        invoice_no = sanitize_data(so_row.get('InvoiceNo'))
                        customer_name = sanitize_data(so_row.get('ClientBusinessName'))
                        invoice_date = sanitize_data(so_row.get('Date'))
                        currency = sanitize_data(so_row.get('CurrencyCode'))
                        total_amount = flt(sanitize_data(so_row.get('SummaryTotal')), precision=2)
                        total_dicount = flt(sanitize_data(so_row.get('SummaryDiscount')), precision=2)
                        # frappe.throw(f"{total_dicount}")

                        if not all([invoice_no, customer_name, invoice_date, currency]):
                            frappe.log_error(f"Missing data in Sales invoice row: {so_row.to_dict()}", "Sales invoice Import Error")
                            continue

                        if not frappe.db.exists("Customer", customer_name):
                            customer = frappe.new_doc("Customer")
                            customer.customer_name = customer_name
                            customer.customer_type = "Company"
                            customer.customer_group = "Commercial"
                            customer.territory = "Saudi Arabia"
                            customer.insert()
                            frappe.db.commit()

                        doc = frappe.new_doc(self.reference_doctype)
                        order_date = so_row['Date']
                        if isinstance(order_date, datetime):
                            doc.set_posting_time = 1
                            doc.posting_date = order_date.strftime("%Y-%m-%d")
                        elif isinstance(order_date, str):
                            doc.set_posting_time = 1
                            doc.posting_date = datetime.strptime(order_date, "%m/%d/%Y").strftime("%Y-%m-%d")
                        else:
                            frappe.throw(f"Invalid date format for Invoice {invoice_no}: {order_date}")
                        
                        doc.customer = customer_name
                        doc.delivery_date = datetime.today().date()
                        doc.currency = currency
                        doc.total = total_amount
                        related_items = items_data[items_data['no'] == invoice_no]

                        for _, item_row in related_items.iterrows():
                            item_code = sanitize_data(item_row.get('item'))
                            unit_price = flt(sanitize_data(item_row.get('unit_price')), precision=2)
                            quantity = flt(sanitize_data(item_row.get('quantity')), precision=2)
                            description = sanitize_data(item_row.get('description'))
                            amount = flt(unit_price * quantity, precision=2)
                            # tax_amount = flt(sanitize_data(item_row.get('tax1_amount')), precision=2) or flt(sanitize_data(item_row.get('tax2_amount')), precision=2)
                            # tax_rate = flt(sanitize_data(item_row.get('tax1_value')), precision=2) or flt(sanitize_data(item_row.get('tax2_value')), precision=2)
                            # frappe.throw(item_tax_template)
                            if not frappe.db.exists("Item", item_code):
                                item = frappe.new_doc("Item")
                                item.item_code = strip(str(item_code))
                                item.item_group = "All Item Groups"
                                item.insert()
                                frappe.db.commit()

                            doc.append("items", {
                                "item_code": item_code,
                                "description": description,
                                "rate": unit_price,
                                "qty": quantity,
                                "amount": amount
                            })
                        doc.taxes_and_charges = self.sales_taxes_and_charges_template
                        tax_rate,account_head = frappe.db.get_value('Sales Taxes and Charges',{"parent":self.sales_taxes_and_charges_template}, ['rate','account_head'],)
                        tax_amount = total_amount * (tax_rate / 100)
                        doc.append("taxes", {
                            "account_head": account_head,
                            "description": "Tax",
                            "charge_type": "On Net Total",
                            "rate": tax_rate,
                            "tax_amount":tax_amount
                        })
                        if total_dicount:
                            doc.apply_discount_on= "Grand Total"
                            doc.discount_amount = total_dicount
                        doc.save()
                        frappe.db.commit()
            if self.reference_doctype == "Purchase Invoice":
                if self.import_data == 1:
                    sales_invoice_file = get_file_path(self.main_file)
                    items_file = get_file_path(self.child_file)

                    if not os.path.exists(sales_invoice_file):
                        frappe.throw(f"Sales invoice file not found: {sales_invoice_file}")
                    if not os.path.exists(items_file):
                        frappe.throw(f"Items file not found: {items_file}")

                    purchase_invoice_data = pd.read_excel(sales_invoice_file)
                    items_data = pd.read_excel(items_file)

                    required_sales_invoice_columns = {'PurchaseOrderNo', 'SupplierBusinessName', 'Date', 'CurrencyCode', 'SummaryTotal'}
                    required_items_columns = {'no', 'item', 'unit_price', 'quantity', 'description', 'tax1_name', 'tax2_name', 'tax1_value', 'tax2_value'}

                    # if not required_sales_invoice_columns.issubset(purchase_invoice_data.columns):
                    #     frappe.throw(f"Missing columns in sales invoice file: {required_sales_invoice_columns - set(purchase_invoice_data.columns)}")
                    # if not required_items_columns.issubset(items_data.columns):
                    #     frappe.throw(f"Missing columns in items file: {required_items_columns - set(items_data.columns)}")

                    for _, po_row in purchase_invoice_data.iterrows():

                        p_invoice_no = str(sanitize_data(po_row.get('PurchaseOrderNo'))).strip()
                        # p_invoice_no = sanitize_data(po_row.get('PurchaseOrderNo'))
                        supplier_name = sanitize_data(po_row.get('SupplierBusinessName'))
                        invoice_date = sanitize_data(po_row.get('Date'))
                        currency = sanitize_data(po_row.get('CurrencyCode'))
                        total_amount = flt(sanitize_data(po_row.get('SummaryTotal')), precision=2)

                        # if not all([p_invoice_no, supplier_name, invoice_date, currency]):
                        #     frappe.log_error(f"Missing data in Sales invoice row: {po_row.to_dict()}", "Sales invoice Import Error")
                        #     continue

                        if not frappe.db.exists("Supplier", supplier_name):
                            supplier = frappe.new_doc("Supplier")
                            supplier.supplier_name = supplier_name
                            supplier.supplier_type = "Company"
                            supplier.supplier_group = "All Supplier Groups"
                            supplier.country = "Saudi Arabia"
                            supplier.insert()
                            frappe.db.commit()

                        doc = frappe.new_doc(self.reference_doctype)
                        order_date = po_row['Date']

                        if isinstance(order_date, datetime):
                            doc.set_posting_time = 1
                            doc.posting_date = order_date.strftime("%Y-%m-%d")
                            frappe.msgprint(f"{doc.posting_date}")
                        doc.supplier =supplier_name
                        doc.set_posting_time = 1
                        doc.posting_date = order_date.strftime("%Y-%m-%d")
                        doc.due_date = order_date.strftime("%Y-%m-%d")
                        doc.currency = currency
                        doc.total = sanitize_data(total_amount)
                        related_items = items_data[items_data['no'].astype(str) == str(p_invoice_no).strip()]
                        for _, item_row in related_items.iterrows():
                            item_code = sanitize_data(strip(str(item_row.get('item'))))
                            unit_price = flt(sanitize_data(item_row.get('unit_price')), precision=2) or 0.0
                            quantity = flt(sanitize_data(item_row.get('quantity')), precision=2) or 0.0
                            description = sanitize_data(item_row.get('description'))
                            # item_tax_template = item_row.get('tax1_name') or item_row.get('tax2_name')
                            # tax_rate = flt(sanitize_data(item_row.get('tax1_value')), precision=2) or flt(sanitize_data(item_row.get('tax2_value')), precision=2)
                            # tax_amount = flt(sanitize_data(item_row.get('tax1_amount')), precision=2) or flt(sanitize_data(item_row.get('tax2_amount')), precision=2)
                            amount = flt(unit_price * quantity, precision=2)

                            if not frappe.db.exists("Item", item_code):
                                item = frappe.new_doc("Item")
                                item.item_code = strip(str(item_code))
                                item.item_group = "All Item Groups"
                                item.description=description
                                item.insert()
                                frappe.db.commit()
                            doc.append("items", {
                                "item_code": item_code,
                                # "schedule_date": doc.schedule_date,
                                "description": description,
                                "rate": unit_price,
                                "qty": quantity,
                                "amount": amount,
                                "item_tax_template":self.item_tax_template
                            })
                        tax_rate,tax_type = frappe.db.get_value('Item Tax Template Detail',{"parent":self.item_tax_template}, ['tax_rate','tax_type'],)
                        tax_amount = total_amount * (tax_rate / 100)
                        doc.append("taxes", {
                            "account_head": tax_type,
                            "description": "Tax",
                            "charge_type": "On Net Total",
                            "rate": tax_rate,
                            "tax_amount":tax_amount
                        })
                        doc.save()
                        frappe.db.commit()
            if self.reference_doctype == "Purchase Order":
                if self.import_data == 1:
                    sales_invoice_file = get_file_path(self.main_file)
                    items_file = get_file_path(self.child_file)

                    if not os.path.exists(sales_invoice_file):
                        frappe.throw(f"Sales invoice file not found: {sales_invoice_file}")
                    if not os.path.exists(items_file):
                        frappe.throw(f"Items file not found: {items_file}")

                    purchase_invoice_data = pd.read_excel(sales_invoice_file)
                    items_data = pd.read_excel(items_file)

                    required_sales_invoice_columns = {'PurchaseOrderNo', 'SupplierBusinessName', 'Date', 'CurrencyCode', 'SummaryTotal'}
                    required_items_columns = {'no', 'item', 'unit_price', 'quantity', 'description', 'tax1_name', 'tax2_name', 'tax1_value', 'tax2_value'}

                    # if not required_sales_invoice_columns.issubset(purchase_invoice_data.columns):
                    #     frappe.throw(f"Missing columns in sales invoice file: {required_sales_invoice_columns - set(purchase_invoice_data.columns)}")
                    # if not required_items_columns.issubset(items_data.columns):
                    #     frappe.throw(f"Missing columns in items file: {required_items_columns - set(items_data.columns)}")

                    for _, po_row in purchase_invoice_data.iterrows():

                        p_invoice_no = str(sanitize_data(po_row.get('PurchaseOrderNo'))).strip()
                        # p_invoice_no = sanitize_data(po_row.get('PurchaseOrderNo'))
                        supplier_name = sanitize_data(po_row.get('SupplierBusinessName'))
                        invoice_date = sanitize_data(po_row.get('Date'))
                        currency = sanitize_data(po_row.get('CurrencyCode'))
                        total_amount = flt(sanitize_data(po_row.get('SummaryTotal')), precision=2)

                        # if not all([p_invoice_no, supplier_name, invoice_date, currency]):
                        #     frappe.log_error(f"Missing data in Sales invoice row: {po_row.to_dict()}", "Sales invoice Import Error")
                        #     continue

                        if not frappe.db.exists("Supplier", supplier_name):
                            supplier = frappe.new_doc("Supplier")
                            supplier.supplier_name = supplier_name
                            supplier.supplier_type = "Company"
                            supplier.supplier_group = "All Supplier Groups"
                            supplier.country = "Saudi Arabia"
                            supplier.insert()
                            frappe.db.commit()

                        doc = frappe.new_doc(self.reference_doctype)
                        order_date = po_row['Date']

                        if isinstance(order_date, datetime):
                            doc.set_posting_time = 1
                            doc.schedule_date = order_date.strftime("%Y-%m-%d")
                        doc.supplier =supplier_name
                        doc.set_posting_time = 1
                        doc.schedule_date = order_date.strftime("%Y-%m-%d")
                        doc.transaction_date = order_date.strftime("%Y-%m-%d")
                        doc.currency = currency
                        doc.total = sanitize_data(total_amount)
                        related_items = items_data[items_data['no'].astype(str) == str(p_invoice_no).strip()]
                        # frappe.msgprint(f"{related_items}")
                        for _, item_row in related_items.iterrows():
                            item_code = sanitize_data(strip(str(item_row.get('item'))))
                            unit_price = flt(sanitize_data(item_row.get('unit_price')), precision=2) or 0.0
                            quantity = flt(sanitize_data(item_row.get('quantity')), precision=2) or 0.0
                            description = sanitize_data(item_row.get('description'))
                            # item_tax_template = item_row.get('tax1_name') or item_row.get('tax2_name')
                            tax_rate = flt(sanitize_data(item_row.get('tax1_value')), precision=2) or flt(sanitize_data(item_row.get('tax2_value')), precision=2)
                            tax_amount = flt(sanitize_data(item_row.get('tax1_amount')), precision=2) or flt(sanitize_data(item_row.get('tax2_amount')), precision=2)
                            frappe.msgprint(f"{tax_rate}")
                            frappe.msgprint(f"{tax_amount}")
                            amount = flt(unit_price * quantity, precision=2)

                            if not frappe.db.exists("Item", item_code):
                                item = frappe.new_doc("Item")
                                item.item_code = strip(str(item_code))
                                item.item_group = "All Item Groups"
                                item.description=description
                                item.insert()
                                frappe.db.commit()
                            doc.append("items", {
                                "item_code": item_code,
                                "schedule_date": doc.schedule_date,
                                "description": description,
                                "rate": unit_price,
                                "qty": quantity,
                                "amount": amount,
                                # "item_tax_template": item_tax_template or ""
                            })
                            doc.append("taxes", {
                                "account_head": self.import_account,
                                "description": "Tax",
                                "charge_type": "Actual",
                                "rate": tax_rate,
                                "tax_amount":tax_amount
                            })
                            doc.save()
                        frappe.db.commit()
def sanitize_data(value):
    """Sanitize data to replace `nan` or invalid values with `None`."""
    if value != value:  # Checks for `nan`
        return None
    return value
