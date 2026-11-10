"""A07: pindahkan semua selfie check-in lama dari public ke private.

- File selfie (nama diawali "selfie_") yang masih public dijadikan private.
  Frappe memindahkan file fisik ke private/files dan mengubah file_url.
- Field custom_foto_selfie pada Employee Checkin ikut diperbarui ke URL baru,
  dan file di-attach ke log check-in supaya HR/karyawan pemiliknya tetap bisa membuka.
- Selfie yatim (tanpa log check-in, temuan A09) juga dijadikan private.
"""

import frappe

SELFIE_FIELD = "custom_foto_selfie"


def get_plan() -> list[dict]:
	files = frappe.get_all(
		"File",
		# catatan: frappe.get_all meng-escape backslash, jadi pola "selfie\_%" tidak cocok;
		# pakai "selfie%" lalu saring awalan "selfie_" di Python.
		filters={"is_private": 0, "is_folder": 0, "file_name": ["like", "selfie%"]},
		fields=["name", "file_name", "file_url", "attached_to_doctype", "attached_to_name"],
	)
	has_field = frappe.get_meta("Employee Checkin").has_field(SELFIE_FIELD)
	plan = []
	for f in files:
		if not f.file_name.startswith("selfie_") or not f.file_url.startswith("/files/"):
			continue
		checkin = None
		if has_field:
			checkin = frappe.db.get_value("Employee Checkin", {SELFIE_FIELD: f.file_url}, "name")
		plan.append(
			{
				"file": f.name,
				"old_url": f.file_url,
				"new_url": "/private/files/" + f.file_url.split("/")[-1],
				"checkin": checkin,
			}
		)
	return plan


def execute(dry_run: bool = False) -> list[dict]:
	plan = get_plan()
	if dry_run:
		return plan

	for item in plan:
		file_doc = frappe.get_doc("File", item["file"])
		file_doc.is_private = 1
		if item["checkin"]:
			file_doc.attached_to_doctype = "Employee Checkin"
			file_doc.attached_to_name = item["checkin"]
			file_doc.attached_to_field = SELFIE_FIELD
		file_doc.flags.ignore_permissions = True
		file_doc.save()

		if item["checkin"]:
			frappe.db.set_value(
				"Employee Checkin", item["checkin"], SELFIE_FIELD, file_doc.file_url, update_modified=False
			)
	return plan
