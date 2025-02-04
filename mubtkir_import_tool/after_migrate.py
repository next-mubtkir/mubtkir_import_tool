import subprocess
import frappe
import os

def after_migrate():
    frappe.logger().info("Running after_migrate: Installing dependencies")
    
    # Get the Frappe Bench directory
    bench_dir = os.path.abspath(os.path.join(frappe.get_site_path(), "../../"))
    
    # Run the bench command in the correct directory
    subprocess.run(
        ["bench", "pip", "install", "-r", f"apps/mubtkir_import_tool/requirements.txt"],
        cwd=bench_dir,  # Set the working directory
        check=True
    )
