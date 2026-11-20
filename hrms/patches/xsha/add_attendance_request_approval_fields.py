"""Koreksi absen 2 lapis (Atasan -> HRD), lihat hrms/xsha/approval.py.

- Custom field Attendance Request: custom_approval_status (Open/Approved/Rejected) dan
  custom_approver (atasan: leave approver karyawan, atau akun Reports To).
- Data lama: yang sudah disubmit = Approved; Draft = Open dengan atasan diisi, lalu dibagikan
  ke atasan supaya bisa dibuka di aplikasi.

Idempotent: aman dijalankan ulang.
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

DT = "Attendance Request"

CUSTOM_FIELDS = {
	DT: [
		{
			"fieldname": "custom_approval_status",
			"label": "Approval Status",
			"fieldtype": "Select",
			"options": "Open\nApproved\nRejected",
			"default": "Open",
			"read_only": 1,
			"in_list_view": 1,
			"in_standard_filter": 1,
			"no_copy": 1,
			"insert_after": "company",
		},
		{
			"fieldname": "custom_approver",
			"label": "Supervisor",
			"fieldtype": "Link",
			"options": "User",
			"read_only": 1,
			"no_copy": 1,
			"insert_after": "custom_approval_status",
		},
	]
}


def execute():
	create_custom_fields(CUSTOM_FIELDS, ignore_validate=True)
	frappe.clear_cache(doctype=DT)

	from hrms.xsha.lembur import get_atasan

	frappe.db.sql(
		f"""update `tab{DT}` set custom_approval_status = 'Approved'
		where docstatus = 1 and ifnull(custom_approval_status, '') in ('', 'Open')"""
	)
	# baris yang dibuat sebelum field ada (NULL) dianggap Open
	frappe.db.sql(f"update `tab{DT}` set custom_approval_status = 'Open' where docstatus = 0 and custom_approval_status is null")
	for row in frappe.get_all(
		DT,
		filters={"docstatus": 0, "custom_approval_status": ["in", ["", "Open"]]},
		fields=["name", "employee", "custom_approver"],
	):
		approver = row.custom_approver or get_atasan(row.employee)
		if approver and approver == frappe.db.get_value("Employee", row.employee, "user_id"):
			approver = None
		frappe.db.set_value(
			DT,
			row.name,
			{"custom_approval_status": "Open", "custom_approver": approver},
			update_modified=False,
		)
		if approver:
			frappe.share.add_docshare(
				DT, row.name, approver, read=1, flags={"ignore_share_permission": True}, notify=0
			)
