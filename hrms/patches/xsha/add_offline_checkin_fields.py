"""Check-in offline aplikasi X-PEOPLE (lihat hrms/xsha/offline.py).

Custom field Employee Checkin:
- custom_offline: log dicatat di HP saat server tidak bisa dihubungi, dikirim belakangan
- custom_offline_id: ID antrean dari HP, supaya pengiriman ulang tidak membuat log ganda
- custom_waktu_terkirim: jam log benar-benar sampai di server (untuk audit HRD)

Idempotent: aman dijalankan ulang.
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

DT = "Employee Checkin"

CUSTOM_FIELDS = {
	DT: [
		{
			"fieldname": "custom_offline",
			"label": "Recorded Offline",
			"fieldtype": "Check",
			"read_only": 1,
			"no_copy": 1,
			"in_standard_filter": 1,
			"description": "Recorded on the phone while the server was unreachable, sent automatically later",
			"insert_after": "log_type",
		},
		{
			"fieldname": "custom_waktu_terkirim",
			"label": "Received by Server",
			"fieldtype": "Datetime",
			"read_only": 1,
			"no_copy": 1,
			"depends_on": "custom_offline",
			"insert_after": "custom_offline",
		},
		{
			"fieldname": "custom_offline_id",
			"label": "Offline ID",
			"fieldtype": "Data",
			"read_only": 1,
			"hidden": 1,
			"no_copy": 1,
			"search_index": 1,
			"insert_after": "custom_waktu_terkirim",
		},
	]
}


def execute():
	create_custom_fields(CUSTOM_FIELDS, ignore_validate=True)
	frappe.clear_cache(doctype=DT)
