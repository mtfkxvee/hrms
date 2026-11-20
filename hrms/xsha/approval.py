"""Persetujuan 2 lapis X-Sha: Atasan -> HRD.

Berlaku untuk Leave Application (cuti/izin/sakit), Shift Request (ganti shift), dan
Attendance Request (koreksi absen). Lembur punya alurnya sendiri di hrms/xsha/lembur.py
dengan urutan yang sama.

Alur (dokumen tetap Draft sampai HRD menyetujui):
    1. Atasan    status Open/Draft -> Approved   (hanya approver yang ditunjuk di pengajuan)
    2. HRD       Approved -> Submit (final)      (hanya role HRD)
    Ditolak di tahap mana pun -> Rejected (cuti/shift langsung disubmit sebagai ditolak,
    koreksi absen tetap Draft dan tidak bisa disubmit).
    Pengajuan tanpa atasan langsung ke tahap HRD.

Koreksi absen tidak punya field status/approver bawaan, jadi memakai custom field
custom_approval_status dan custom_approver (dibuat patch hrms.patches.xsha.add_attendance_request_approval_fields).
"""

import frappe
from frappe import _
from frappe.utils import cint

HRD_ROLE = "HRD"
APPROVED, REJECTED = "Approved", "Rejected"

CONFIG = {
	"Leave Application": frappe._dict(
		approver="leave_approver", status="status", open="Open", label=_("pengajuan izin/cuti")
	),
	"Shift Request": frappe._dict(
		approver="approver", status="status", open="Draft", label=_("pengajuan ganti shift")
	),
	"Attendance Request": frappe._dict(
		approver="custom_approver", status="custom_approval_status", open="Open", label=_("koreksi absen")
	),
}

SUPERVISOR, HRD = "supervisor", "hrd"


def is_hrd(user: str | None = None) -> bool:
	user = user or frappe.session.user
	return user == "Administrator" or HRD_ROLE in frappe.get_roles(user)


def hrd_users() -> list[str]:
	"""Semua user aktif yang punya role HRD (bukan orang tertentu)."""
	users = frappe.get_all("Has Role", filters={"role": HRD_ROLE, "parenttype": "User"}, pluck="parent")
	users = [u for u in users if u not in ("Administrator", "Guest")]
	return frappe.get_all("User", filters={"name": ["in", users or [""]], "enabled": 1}, pluck="name")


def other_hrd_users(employee: str) -> list[str]:
	"""User role HRD selain pemohon (HRD tidak boleh menyetujui pengajuannya sendiri)."""
	pemohon = frappe.db.get_value("Employee", employee, "user_id")
	return [u for u in hrd_users() if (u or "").lower() != (pemohon or "").lower()]


def supervisor_is_final(employee: str) -> bool:
	"""Tidak ada orang HRD lain yang bisa menyetujui (mis. pemohonnya satu-satunya HRD):
	persetujuan atasan langsung menjadi persetujuan akhir supaya pengajuan tidak macet."""
	return not other_hrd_users(employee)


def final_approver_users(employee: str, approver: str | None) -> list[str]:
	"""Siapa yang memproses tahap HRD: semua role HRD selain pemohon, atau atasan kalau tidak ada."""
	return other_hrd_users(employee) or ([approver] if approver else [])


def _same_user(a, b) -> bool:
	return (a or "").strip().lower() == (b or "").strip().lower()


def _employee_user(employee: str) -> str | None:
	return frappe.db.get_value("Employee", employee, "user_id")


def _can_final_approve(doc, user) -> bool:
	"""Boleh memberi persetujuan akhir (tahap HRD)."""
	if is_hrd(user):
		return True
	cfg = CONFIG[doc.doctype]
	return supervisor_is_final(doc.employee) and _same_user(user, doc.get(cfg.approver))


def _skip_checks() -> bool:
	return frappe.session.user == "Administrator" or bool(
		frappe.flags.in_import or frappe.flags.in_patch or frappe.flags.in_migrate or frappe.flags.in_install
	)


def _stage_for(status, approver) -> str | None:
	if status == APPROVED:
		return HRD
	if status == REJECTED:
		return None
	# Open / Draft (atau kosong pada koreksi absen lama)
	return SUPERVISOR if approver else HRD


def get_stage(doc, status=None) -> str | None:
	"""Tahap yang sedang ditunggu: "supervisor", "hrd", atau None (sudah diputuskan / bukan Draft)."""
	cfg = CONFIG[doc.doctype]
	if doc.docstatus != 0:
		return None
	return _stage_for(doc.get(cfg.status) if status is None else status, doc.get(cfg.approver))


def get_actions(doc, user: str | None = None) -> dict:
	user = user or frappe.session.user
	cfg = CONFIG[doc.doctype]
	stage = get_stage(doc)
	allowed = False
	if stage and user != _employee_user(doc.employee):
		if user == "Administrator":
			allowed = True
		elif stage == SUPERVISOR:
			allowed = _same_user(user, doc.get(cfg.approver))
		else:
			allowed = _can_final_approve(doc, user)
	return {
		"stage": stage,
		"approver": doc.get(cfg.approver),
		"can_approve": allowed,
		"can_reject": allowed,
	}


# ---------------------------------------------------------------------------
# API untuk aplikasi HRMS (tombol Approve / Reject)
# ---------------------------------------------------------------------------


def _get_doc(doctype: str, name: str):
	if doctype not in CONFIG:
		frappe.throw(_("Jenis pengajuan tidak didukung."))
	doc = frappe.get_doc(doctype, name)
	doc.check_permission("read")
	return doc


@frappe.whitelist()
def get_approval_actions(doctype: str, name: str) -> dict:
	return get_actions(_get_doc(doctype, name))


@frappe.whitelist(methods=["POST"])
def approve(doctype: str, name: str) -> dict:
	doc = _get_doc(doctype, name)
	actions = get_actions(doc)
	if not actions["can_approve"]:
		_throw_not_allowed(doc, actions["stage"])
	cfg = CONFIG[doctype]
	doc.flags.ignore_permissions = True
	doc.set(cfg.status, APPROVED)
	if actions["stage"] == SUPERVISOR and not is_hrd() and not supervisor_is_final(doc.employee):
		doc.save()  # lanjut ke tahap HRD
	else:
		# HRD, atasan yang juga HRD, atau atasan saat tidak ada HRD lain = persetujuan akhir
		doc.submit()
	return {"stage": get_stage(doc), "docstatus": doc.docstatus}


@frappe.whitelist(methods=["POST"])
def reject(doctype: str, name: str) -> dict:
	doc = _get_doc(doctype, name)
	actions = get_actions(doc)
	if not actions["can_reject"]:
		_throw_not_allowed(doc, actions["stage"])
	cfg = CONFIG[doctype]
	doc.flags.ignore_permissions = True
	doc.set(cfg.status, REJECTED)
	if doctype == "Attendance Request":
		doc.save()  # koreksi absen ditolak tidak disubmit (submit = absensi dibuat)
	else:
		doc.submit()
	return {"stage": None, "docstatus": doc.docstatus}


def _throw_not_allowed(doc, stage):
	cfg = CONFIG[doc.doctype]
	if not stage:
		frappe.throw(_("Pengajuan ini sudah diproses."))
	if frappe.session.user == _employee_user(doc.employee):
		frappe.throw(
			_("Anda tidak boleh menyetujui atau menolak {0} milik sendiri.").format(cfg.label),
			title=_("Persetujuan Sendiri Tidak Diizinkan"),
		)
	if stage == SUPERVISOR:
		frappe.throw(
			_("{0} ini harus disetujui dulu oleh atasan ({1}), baru diteruskan ke HRD.").format(
				cfg.label.capitalize(), frappe.bold(doc.get(cfg.approver))
			),
			title=_("Menunggu Atasan"),
		)
	frappe.throw(_("Tahap ini hanya bisa diproses oleh HRD."), title=_("Bukan HRD"))


# ---------------------------------------------------------------------------
# doc_events: jaga jalur lain (desk, setValue dari aplikasi) supaya tetap 2 lapis
# ---------------------------------------------------------------------------


def validate_decision(doc):
	"""Dipanggil di validate: perubahan status keputusan harus oleh orang di tahap yang benar."""
	if _skip_checks():
		return
	cfg = CONFIG[doc.doctype]
	before = None if doc.is_new() else doc.get_doc_before_save()
	if before is not None and before.docstatus != 0:
		return
	new = doc.get(cfg.status) or cfg.open
	prev = (before.get(cfg.status) if before is not None else None) or cfg.open
	if new == prev:
		return

	user = frappe.session.user
	if user == _employee_user(doc.employee):
		frappe.throw(
			_("Anda tidak boleh menyetujui atau menolak {0} milik sendiri.").format(cfg.label),
			title=_("Persetujuan Sendiri Tidak Diizinkan"),
		)

	prev_stage = _stage_for(prev, (before if before is not None else doc).get(cfg.approver))
	if prev_stage == SUPERVISOR:
		if not _same_user(user, doc.get(cfg.approver)):
			_throw_not_allowed(doc, SUPERVISOR)
	elif not _can_final_approve(doc, user):
		# tahap HRD, atau mengubah keputusan yang sudah ada
		_throw_not_allowed(doc, HRD)


def validate_submit(doc):
	"""Dipanggil di before_submit: persetujuan akhir hanya oleh HRD."""
	if _skip_checks():
		return
	cfg = CONFIG[doc.doctype]
	user = frappe.session.user
	status = doc.get(cfg.status) or cfg.open

	if user == _employee_user(doc.employee):
		frappe.throw(
			_("Anda tidak boleh menyetujui atau menolak {0} milik sendiri.").format(cfg.label),
			title=_("Persetujuan Sendiri Tidak Diizinkan"),
		)

	if status == REJECTED:
		if doc.doctype == "Attendance Request":
			frappe.throw(_("Koreksi absen yang ditolak tidak bisa disubmit."))
		return  # siapa yang menolak sudah dicek di validate_decision

	if status != APPROVED:
		# Open/Draft: hanya boleh langsung submit kalau tidak ada atasan (tahap HRD)
		if doc.get(cfg.approver):
			_throw_not_allowed(doc, SUPERVISOR)
		if doc.doctype == "Attendance Request":
			doc.set(cfg.status, APPROVED)

	if not _can_final_approve(doc, user):
		_throw_not_allowed(doc, HRD)


# ---------------------------------------------------------------------------
# Daftar "To Approve" dan pengingat
# ---------------------------------------------------------------------------


def pending_filters(doctype: str, user: str) -> list[dict]:
	"""Filter pengajuan yang menunggu keputusan `user` (atasan dan/atau HRD)."""
	cfg = CONFIG[doctype]
	filters = [{"docstatus": 0, cfg.status: cfg.open, cfg.approver: user}]
	if is_hrd(user):
		filters.append({"docstatus": 0, cfg.status: APPROVED})
		filters.append({"docstatus": 0, cfg.status: cfg.open, cfg.approver: ["is", "not set"]})
	return filters


def get_pending_for_user(doctype: str, employee: str, fields: list, limit=None, order_by="creation desc"):
	user = frappe.session.user
	rows, seen = [], set()
	for filters in pending_filters(doctype, user):
		if employee:
			filters["employee"] = ["!=", employee]
		for row in frappe.get_all(doctype, filters=filters, fields=fields, order_by=order_by, limit=limit):
			if row.name not in seen:
				seen.add(row.name)
				rows.append(row)
	# tahap HRD tanpa HRD lain (mis. pengajuan milik satu-satunya HRD): atasan yang memproses
	cfg = CONFIG[doctype]
	for row in frappe.get_all(
		doctype,
		filters={"docstatus": 0, cfg.status: APPROVED, cfg.approver: user},
		fields=fields,
		order_by=order_by,
	):
		if row.name not in seen and supervisor_is_final(row.employee):
			seen.add(row.name)
			rows.append(row)
	key = order_by.split()[0]
	rows.sort(key=lambda r: (str(r.get(key) or ""), str(r.get("creation") or "")), reverse=order_by.endswith("desc"))
	return rows[: cint(limit)] if limit else rows


def get_all_pending() -> list[tuple[str, dict]]:
	"""[(user, row)] semua pengajuan yang menunggu, untuk email ringkasan harian."""
	out = []
	for doctype, cfg in CONFIG.items():
		if not frappe.get_meta(doctype).has_field(cfg.status):
			continue
		fields = [
			"name",
			"employee",
			"employee_name",
			"from_date",
			"to_date",
			f"{cfg.approver} as approver",
			f"{cfg.status} as status",
		]
		for row in frappe.get_all(
			doctype, filters={"docstatus": 0, cfg.status: ["in", [cfg.open, APPROVED]]}, fields=fields, order_by="from_date asc"
		):
			row.doctype = doctype
			if row.status == cfg.open and row.approver:
				out.append((row.approver, frappe._dict(row, stage=SUPERVISOR)))
			else:
				users = final_approver_users(row.employee, row.approver)
				out.extend((u, frappe._dict(row, stage=HRD)) for u in users)
	return out


# ---------------------------------------------------------------------------
# Koreksi absen: atasan dan status
# ---------------------------------------------------------------------------


def attendance_request_validate(doc, method=None):
	if not doc.meta.has_field("custom_approver"):
		return  # patch custom field belum jalan
	if doc.is_new():
		from hrms.xsha.lembur import get_atasan

		# atasan selalu dari data karyawan (leave approver / Reports To), tidak dari isian pemohon
		if not (doc.get("custom_approver") and (_skip_checks() or is_hrd())):
			atasan = get_atasan(doc.employee)
			doc.custom_approver = None if _same_user(atasan, _employee_user(doc.employee)) else atasan
		if not doc.get("custom_approval_status"):
			doc.custom_approval_status = "Open"
	elif doc.has_value_changed("custom_approver") and not (_skip_checks() or is_hrd()):
		frappe.throw(_("Atasan koreksi absen hanya bisa diubah oleh HRD."))
	validate_decision(doc)


def attendance_request_on_update(doc, method=None):
	"""Bagikan dokumen ke atasan supaya bisa dibuka di aplikasi (seperti cuti/shift)."""
	notify_hrd_stage(doc)
	approver = doc.get("custom_approver")
	if approver and not frappe.has_permission(doc=doc, ptype="read", user=approver):
		frappe.share.add_docshare(
			doc.doctype, doc.name, approver, read=1, flags={"ignore_share_permission": True}, notify=0
		)


# ---------------------------------------------------------------------------
# Notifikasi aplikasi ke karyawan
# ---------------------------------------------------------------------------


def pwa_notification_before_insert(doc, method=None):
	"""Notifikasi bawaan "has been Approved" terkirim saat atasan menyetujui (status -> Approved),
	padahal pengajuan masih menunggu HRD. Ubah pesannya supaya karyawan tidak salah paham."""
	if doc.reference_document_type not in CONFIG or not doc.reference_document_name:
		return
	cfg = CONFIG[doc.reference_document_type]
	values = frappe.db.get_value(
		doc.reference_document_type,
		doc.reference_document_name,
		["docstatus", "employee", cfg.status],
		as_dict=True,
	)
	if not values or doc.to_user != _employee_user(values.employee):
		return  # hanya notifikasi ke pemohon (bukan notifikasi ke HRD)
	if values.docstatus == 0 and values.get(cfg.status) == APPROVED:
		doc.message = (
			f"{frappe.bold('Your')} {frappe.bold(doc.reference_document_type)} {doc.reference_document_name}"
			f" has been approved by your supervisor ({frappe.bold(frappe.utils.get_fullname(doc.from_user))})"
			" and is waiting for HR approval"
		)


def notify_final_approval(doc, method=None):
	"""on_submit: kabari karyawan di aplikasi bahwa HRD sudah menyetujui (persetujuan akhir)."""
	cfg = CONFIG[doc.doctype]
	if doc.get(cfg.status) != APPROVED or not frappe.db.exists("DocType", "PWA Notification"):
		return
	if doc.doctype != "Attendance Request" and doc.has_value_changed(cfg.status):
		return  # status baru berubah di submit ini: notifikasi bawaan "Approved" sudah terkirim
	from_user, to_user = frappe.session.user, _employee_user(doc.employee)
	if not to_user or to_user == from_user:
		return
	notification = frappe.new_doc("PWA Notification")
	notification.from_user = from_user
	notification.to_user = to_user
	notification.message = (
		f"{frappe.bold('Your')} {frappe.bold(doc.doctype)} {doc.name} has been {frappe.bold('Approved')}"
		f" by HR ({frappe.bold(frappe.utils.get_fullname(from_user))})"
	)
	notification.reference_document_type = doc.doctype
	notification.reference_document_name = doc.name
	notification.insert(ignore_permissions=True)


def notify_hrd_stage(doc, method=None):
	"""on_update: setelah atasan menyetujui, kabari orang HRD di aplikasi (selain WA dan email harian)."""
	cfg = CONFIG[doc.doctype]
	if doc.docstatus != 0 or doc.get(cfg.status) != APPROVED or not doc.has_value_changed(cfg.status):
		return
	if not frappe.db.exists("DocType", "PWA Notification"):
		return
	from_user = frappe.session.user
	for user in final_approver_users(doc.employee, doc.get(cfg.approver)):
		if user == from_user:
			continue
		notification = frappe.new_doc("PWA Notification")
		notification.from_user = from_user
		notification.to_user = user
		notification.message = (
			f"{frappe.bold(doc.employee_name)}'s {frappe.bold(doc.doctype)} {doc.name} was approved by the"
			" supervisor and is waiting for your approval (HR)"
		)
		notification.reference_document_type = doc.doctype
		notification.reference_document_name = doc.name
		notification.insert(ignore_permissions=True)
