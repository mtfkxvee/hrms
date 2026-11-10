"""Edit profil karyawan dari aplikasi PWA.

Karyawan hanya boleh mengubah field di SELF_EDITABLE_FIELDS dan foto profilnya.
Data identitas, pekerjaan, rekening, dan approver tetap diubah oleh HR.
Aturan yang sama juga dipaksakan di server (rules.employee_validate) sehingga
role Employee Self Service tidak bisa mengubah field lain lewat API.
"""

import re

import frappe
from frappe import _
from frappe.utils import validate_email_address

from hrms.xsha.checkin import decode_photo

# urutan = urutan tampil di form
SELF_EDITABLE_FIELDS = (
	"cell_number",
	"personal_email",
	"prefered_contact_email",
	"current_address",
	"current_accommodation_type",
	"permanent_address",
	"permanent_accommodation_type",
	"person_to_be_contacted",
	"emergency_phone_number",
	"relation",
	"marital_status",
	"blood_group",
)
# field yang diisi otomatis oleh sistem saat karyawan menyimpan
SELF_DERIVED_FIELDS = ("image", "prefered_email", "employee_name")

SECTIONS = (
	("Kontak", ("cell_number", "personal_email", "prefered_contact_email")),
	("Alamat", ("current_address", "current_accommodation_type", "permanent_address", "permanent_accommodation_type")),
	("Kontak Darurat", ("person_to_be_contacted", "emergency_phone_number", "relation")),
	("Data Pribadi", ("marital_status", "blood_group")),
)
PHONE_FIELDS = ("cell_number", "emergency_phone_number")
PHONE_RE = re.compile(r"^\+?[0-9][0-9 \-]{6,18}$")
PROFILE_PHOTO_PREFIX = "profile_"


def _my_employee() -> str:
	employee = frappe.db.get_value("Employee", {"user_id": frappe.session.user, "status": "Active"}, "name")
	if not employee:
		frappe.throw(_("Akun Anda belum terhubung ke data karyawan aktif. Hubungi HR."))
	return employee


@frappe.whitelist()
def get_my_profile() -> dict:
	employee = _my_employee()
	meta = frappe.get_meta("Employee")
	values = frappe.db.get_value("Employee", employee, list(SELF_EDITABLE_FIELDS) + ["image"], as_dict=True)
	sections = []
	for title, fieldnames in SECTIONS:
		fields = []
		for fieldname in fieldnames:
			df = meta.get_field(fieldname)
			if not df:
				continue
			fields.append(
				{
					"fieldname": fieldname,
					"label": _(df.label),
					"fieldtype": df.fieldtype,
					"options": [o for o in (df.options or "").split("\n") if o] if df.fieldtype == "Select" else [],
					"value": values.get(fieldname) or "",
				}
			)
		sections.append({"title": _(title), "fields": fields})
	return {"employee": employee, "image": values.image, "sections": sections}


def _clean(fieldname: str, value):
	value = (value or "").strip() if isinstance(value, str) else value
	if not value:
		return None
	df = frappe.get_meta("Employee").get_field(fieldname)
	if df.fieldtype == "Select":
		options = [o for o in (df.options or "").split("\n") if o]
		if value not in options:
			frappe.throw(_("Pilihan {0} tidak valid untuk {1}.").format(frappe.bold(value), _(df.label)))
	if fieldname == "personal_email":
		validate_email_address(value, throw=True)
	if fieldname in PHONE_FIELDS and not PHONE_RE.match(value):
		frappe.throw(_("Nomor {0} tidak valid. Gunakan angka, boleh diawali +.").format(_(df.label)))
	if df.fieldtype == "Data" and len(value) > 140:
		frappe.throw(_("{0} terlalu panjang.").format(_(df.label)))
	return value


@frappe.whitelist(methods=["POST"])
def update_my_profile(data) -> dict:
	data = frappe.parse_json(data) or {}
	unknown = set(data) - set(SELF_EDITABLE_FIELDS)
	if unknown:
		frappe.throw(_("Field berikut tidak boleh diubah sendiri: {0}. Hubungi HR.").format(", ".join(sorted(unknown))))

	doc = frappe.get_doc("Employee", _my_employee())
	changed = []
	for fieldname, value in data.items():
		value = _clean(fieldname, value)
		if (doc.get(fieldname) or None) != value:
			doc.set(fieldname, value)
			changed.append(fieldname)

	if changed:
		doc.flags.ignore_permissions = True
		doc.save()
	return {"changed": changed}


@frappe.whitelist(methods=["POST"])
def update_my_photo(photo: str) -> dict:
	content = decode_photo(photo)
	doc = frappe.get_doc("Employee", _my_employee())
	old_files = frappe.get_all(
		"File",
		filters={
			"attached_to_doctype": "Employee",
			"attached_to_name": doc.name,
			"attached_to_field": "image",
			"file_name": ["like", PROFILE_PHOTO_PREFIX + "%"],
		},
		pluck="name",
	)

	# foto profil dibuat public supaya avatar tampil untuk rekan kerja dan approver
	file_doc = frappe.get_doc(
		{
			"doctype": "File",
			"file_name": f"{PROFILE_PHOTO_PREFIX}{doc.name}_{frappe.generate_hash(length=8)}.jpg",
			"is_private": 0,
			"content": content,
			"attached_to_doctype": "Employee",
			"attached_to_name": doc.name,
			"attached_to_field": "image",
		}
	)
	file_doc.flags.ignore_permissions = True
	file_doc.insert()

	doc.image = file_doc.file_url
	doc.flags.ignore_permissions = True
	doc.save()

	if doc.user_id:
		frappe.db.set_value("User", doc.user_id, "user_image", file_doc.file_url)
		frappe.clear_cache(user=doc.user_id)

	# hapus foto profil lama yang dibuat lewat fitur ini
	for name in old_files:
		frappe.delete_doc("File", name, ignore_permissions=True, force=True)

	return {"image": file_doc.file_url}
