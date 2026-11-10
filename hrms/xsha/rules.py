"""Aturan server tambahan X-Sha untuk absensi, ganti shift, dan izin/sakit.

Dipasang lewat doc_events di hrms/hooks.py supaya file inti HRMS tidak diubah.
Setiap fungsi menyebut ID temuan dari dokumen "Analisis HRMS V1".
"""

import frappe
from frappe import _
from frappe.utils import add_days, get_datetime, getdate, now_datetime

from hrms.hr.utils import get_distance_between_coordinates

# Role yang boleh memproses pengajuan karyawan lain selain approver yang ditunjuk.
HR_ROLES = ("HR Manager", "HR User")
DECIDED_STATUSES = ("Approved", "Rejected")


def _employee_user(employee: str) -> str | None:
	return frappe.db.get_value("Employee", employee, "user_id")


def _is_hr(user: str | None = None) -> bool:
	user = user or frappe.session.user
	if user == "Administrator":
		return True
	return bool(set(HR_ROLES) & set(frappe.get_roles(user)))


def _is_deciding(doc) -> bool:
	"""True jika dokumen sedang disetujui/ditolak (status berubah, atau di-submit)."""
	if doc.status not in DECIDED_STATUSES:
		return False
	if doc.docstatus == 1:
		return True
	return doc.is_new() or doc.has_value_changed("status")


def _guard_decider(doc, approver_field: str, label: str):
	"""Tolak keputusan dari pemohon sendiri, atau dari orang selain approver / HR."""
	user = frappe.session.user
	if user == "Administrator":
		return

	if user == _employee_user(doc.employee):
		frappe.throw(
			_("Anda tidak boleh menyetujui atau menolak {0} milik sendiri.").format(label),
			title=_("Persetujuan Sendiri Tidak Diizinkan"),
		)

	approver = doc.get(approver_field)
	if user != approver and not _is_hr(user):
		frappe.throw(
			_("Hanya approver yang ditunjuk ({0}) atau HR yang boleh memproses {1} ini.").format(
				frappe.bold(approver or "-"), label
			),
			title=_("Bukan Approver"),
		)


# ---------------------------------------------------------------------------
# Employee Checkin
# ---------------------------------------------------------------------------


def checkin_before_validate(doc, method=None):
	"""A17: check-in milik sendiri selalu memakai jam server.

	Berlaku untuk semua role (termasuk HR) saat membuat log untuk dirinya sendiri.
	Koreksi jam milik sendiri harus lewat Attendance Request. Log dari mesin absen
	atau dibuat HR untuk karyawan lain tidak terpengaruh.
	"""
	if not doc.is_new() or frappe.session.user in ("Administrator", "Guest"):
		return
	if frappe.flags.in_import or frappe.flags.in_patch:
		return
	if _employee_user(doc.employee) == frappe.session.user:
		doc.time = now_datetime().replace(microsecond=0)


def get_branch_shift_location(employee: str) -> dict | None:
	"""Shift Location milik cabang karyawan (field Shift Location.branch)."""
	branch = frappe.db.get_value("Employee", employee, "branch")
	if not branch or not frappe.get_meta("Shift Location").has_field("branch"):
		return None
	return frappe.db.get_value(
		"Shift Location",
		{"branch": branch},
		["name", "checkin_radius", "latitude", "longitude"],
		as_dict=True,
	)


def checkin_validate(doc, method=None):
	"""A06: radius juga dicek dari lokasi cabang karyawan.

	Validasi bawaan hanya membaca shift_location pada Shift Assignment aktif. Karyawan
	dengan default shift atau assignment hasil Shift Request (tanpa lokasi) lolos.
	Di sini, jika assignment tidak punya lokasi, dipakai Shift Location cabang karyawan.
	"""
	if not doc.is_new():
		return
	if not frappe.db.get_single_value("HR Settings", "allow_geolocation_tracking"):
		return

	has_assignment_location = frappe.get_all(
		"Shift Assignment",
		filters={
			"employee": doc.employee,
			"shift_type": doc.shift,
			"start_date": ["<=", doc.time],
			"shift_location": ["is", "set"],
			"docstatus": 1,
			"status": "Active",
		},
		or_filters=[["end_date", ">=", doc.time], ["end_date", "is", "not set"]],
		limit=1,
	)
	if has_assignment_location:
		return  # sudah dicek oleh validasi bawaan

	location = get_branch_shift_location(doc.employee)
	if not location or not location.checkin_radius or location.checkin_radius <= 0:
		return

	if not (doc.latitude or doc.longitude):
		frappe.throw(_("Lokasi (latitude dan longitude) wajib untuk check-in."))

	distance = get_distance_between_coordinates(
		location.latitude, location.longitude, doc.latitude, doc.longitude
	)
	if distance > location.checkin_radius:
		from hrms.hr.doctype.employee_checkin.employee_checkin import CheckinRadiusExceededError

		frappe.throw(
			_("Anda berada {0} meter dari {1}. Check-in hanya boleh dalam radius {2} meter.").format(
				int(distance), location.name, location.checkin_radius
			),
			exc=CheckinRadiusExceededError,
		)


# ---------------------------------------------------------------------------
# Shift Request
# ---------------------------------------------------------------------------


def shift_request_validate(doc, method=None):
	"""S05: blokir persetujuan sendiri dan persetujuan oleh non-approver."""
	if _is_deciding(doc):
		_guard_decider(doc, "approver", _("pengajuan ganti shift"))


def shift_request_before_submit(doc, method=None):
	_guard_decider(doc, "approver", _("pengajuan ganti shift"))


def shift_request_on_submit(doc, method=None):
	"""S06: setelah ganti shift disetujui, log check-in di rentang itu dihitung ulang shift-nya."""
	if doc.status != "Approved":
		return
	refresh_checkin_shifts(doc.employee, doc.from_date, doc.to_date)


def refresh_checkin_shifts(employee: str, from_date, to_date=None) -> list[str]:
	"""Hitung ulang shift pada log check-in yang belum menjadi Attendance."""
	end = getdate(to_date) if to_date else getdate()
	logs = frappe.get_all(
		"Employee Checkin",
		filters={
			"employee": employee,
			"time": ["between", [get_datetime(from_date), get_datetime(add_days(end, 2))]],
			"attendance": ["is", "not set"],
		},
		pluck="name",
	)
	fields = ("shift", "offshift", "shift_start", "shift_end", "shift_actual_start", "shift_actual_end")
	updated = []
	for name in logs:
		log = frappe.get_doc("Employee Checkin", name)
		before = {f: log.get(f) for f in fields}
		log.fetch_shift()
		after = {f: log.get(f) for f in fields}
		if after != before:
			frappe.db.set_value("Employee Checkin", name, after, update_modified=False)
			updated.append(name)
	return updated


# ---------------------------------------------------------------------------
# Leave Application
# ---------------------------------------------------------------------------


def get_valid_leave_approvers(employee: str) -> set[str]:
	"""Approver sah: leave_approver di data karyawan + approver departemen (termasuk induknya)."""
	from hrms.api import get_department_approvers

	leave_approver, department = frappe.db.get_value(
		"Employee", employee, ["leave_approver", "department"]
	)
	approvers = {a["name"] for a in get_department_approvers(department, "leave_approvers")}
	if leave_approver:
		approvers.add(leave_approver)
	return approvers


def leave_application_validate(doc, method=None):
	"""I06: approver harus sesuai data karyawan; yang memutuskan harus approver itu atau HR."""
	if doc.leave_approver and (doc.is_new() or doc.has_value_changed("leave_approver")):
		valid = get_valid_leave_approvers(doc.employee)
		if doc.leave_approver not in valid and not _is_hr():
			frappe.throw(
				_("{0} bukan approver cuti untuk karyawan ini.").format(frappe.bold(doc.leave_approver)),
				title=_("Approver Tidak Sah"),
			)

	if _is_deciding(doc):
		_guard_decider(doc, "leave_approver", _("pengajuan izin/cuti"))


# ---------------------------------------------------------------------------
# Attendance Request
# ---------------------------------------------------------------------------


def attendance_request_before_submit(doc, method=None):
	"""A20: HR tidak boleh menyetujui koreksi absen miliknya sendiri."""
	if frappe.session.user == "Administrator":
		return
	if _employee_user(doc.employee) == frappe.session.user:
		frappe.throw(
			_("Anda tidak boleh menyetujui koreksi absen milik sendiri."),
			title=_("Persetujuan Sendiri Tidak Diizinkan"),
		)
