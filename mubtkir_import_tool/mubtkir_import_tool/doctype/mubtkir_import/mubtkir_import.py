# Copyright (c) 2024, Nextash and contributors
# For license information, please see license.txt




from rq.timeouts import JobTimeoutException
import frappe
from frappe.model.document import Document
from frappe.core.doctype.data_import.importer import Importer,ImportFile

class MubtkirImport(Document):
    
    # pass
    @frappe.whitelist()
    def get_preview_from_template(self, import_file=None, google_sheets_url=None):
        if import_file:
            self.import_file = import_file

        # if google_sheets_url:
        #     self.google_sheets_url = google_sheets_url

        if not (self.import_file ):
            return
        frappe.msgprint("sss")
        i = self.get_importer()
        return i.get_data_for_import_preview()
    
    def get_importer(self):
        return Importer(self.reference_doctype, data_import=self)
    
    @frappe.whitelist()
    def form_start_import(data_import: str):
        return frappe.get_doc("Mubtkir Import", data_import).start_import()


    # def validate(self):
    
    #     frappe.msgprint(f"{self.mubtkir_import_preview}")
    
    #     # pass



@frappe.whitelist()
def get_preview_from_template(data_import, import_file=None, google_sheets_url=None):
	return frappe.get_doc("Mubtkir Import", data_import).get_preview_from_template(
		import_file, google_sheets_url
	)

def start_import(data_import):
	"""This method runs in background job"""
	data_import = frappe.get_doc("Mubtkir Import", data_import)
	try:
		i = Importer(data_import.reference_doctype, data_import=data_import)
		i.import_data()
	except JobTimeoutException:
		frappe.db.rollback()
		data_import.db_set("status", "Timed Out")
	except Exception:
		frappe.db.rollback()
		data_import.db_set("status", "Error")
		data_import.log_error("Data import failed")
	finally:
		frappe.flags.in_import = False

	frappe.publish_realtime("data_import_refresh", {"data_import": data_import.name})




# @frappe.whitelist()
# def preview_data(docname):
#     doc = frappe.get_doc("Mubtkir Import", docname)

#     if not doc.import_file or not doc.child_table:
#         frappe.throw("Please attach both Main File and Child Table File.")
#     import_file_path = get_file_path(doc.import_file)
#     child_file_path = get_file_path(doc.child_table)

#     try:
#         sales_order_data = pd.read_excel(import_file_path)
#         items_data = pd.read_excel(child_file_path)
#         frappe.msgprint(f"Columns in sales order file: {list(sales_order_data.columns)}")
#         frappe.msgprint(f"Columns in items file: {list(items_data.columns)}")
#         main_html = sales_order_data.to_html(classes="table table-bordered", index=False)
#         child_html = items_data.to_html(classes="table table-bordered", index=False)
#         doc.status = "Completed"
#         return f"<b>Main Data:</b>{main_html}<br><b>Child Data:</b>{child_html}"
#     except Exception as e:
#         frappe.log_error(frappe.get_traceback(), "Preview Data Error")
#         frappe.throw("An error occurred while processing the files.")

# @frappe.whitelist()
# def import_data(docname):
    # doc = frappe.get_doc("Mubtkir Import", docname)
    # import_file_path = get_file_path(doc.import_file)
    # child_file_path = get_file_path(doc.child_table)
    
    # try:
    #     # Read data
    #     sales_order_data = pd.read_excel(import_file_path)
    #     items_data = pd.read_excel(child_file_path)
        
    #     # Validation
    #     required_main_fields = ["Customer", "Transaction Date"]
    #     required_child_fields = ["Parent", "Item Code", "Quantity", "Rate"]
        
    #     for field in required_main_fields:
    #         if field not in sales_order_data.columns:
    #             frappe.throw(f"Missing required field: {field} in Main File.")
        
    #     for field in required_child_fields:
    #         if field not in items_data.columns:
    #             frappe.throw(f"Missing required field: {field} in Child Table File.")
        
    #     # Import Logic
    #     for _, row in sales_order_data.iterrows():
    #         sales_order = frappe.new_doc("Sales Order")
    #         sales_order.customer = row["Customer"]
    #         sales_order.transaction_date = row["Transaction Date"]
    #         sales_order.save()
            
    #         related_items = items_data[items_data["Parent"] == row["Order ID"]]
    #         for _, item_row in related_items.iterrows():
    #             sales_order.append("items", {
    #                 "item_code": item_row["Item Code"],
    #                 "qty": item_row["Quantity"],
    #                 "rate": item_row["Rate"]
    #             })
            
    #         sales_order.submit()
        
    #     # Update status
    #     doc.status = "Completed"
    #     doc.save()
    #     frappe.msgprint("Data imported successfully!")
    
    # except Exception as e:
    #     frappe.log_error(frappe.get_traceback(), "Import Data Error")
    #     doc.status = "Error"
    #     doc.save()
    #     frappe.throw(f"An error occurred: {str(e)}")