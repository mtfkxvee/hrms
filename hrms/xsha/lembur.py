"""Lembur atas permintaan karyawan (SOP-XSHA/HRD/06/X/2026) di aplikasi HRMS.

Alur status Overtime Request:
    Pending Supervisor -> Pending HR -> Approved (= SPL) -> In Progress
    -> Pending Confirmation -> Completed
    (bisa berakhir Rejected / Cancelled)

Perubahan status hanya lewat fungsi aksi di file ini (whitelisted), supaya aturan
siapa-boleh-apa dijaga di server. Karyawan hanya membuat pengajuan dan mengubahnya
selama masih Pending Supervisor.

Aturan hitung (SOP):
- jam dihitung dari waktu nyata Mulai/Selesai Lembur
- tiap jam penuh dihitung 1; sisa >= 45 menit dibulatkan 1 jam, < 45 menit tidak dihitung
- maksimal 3 jam per hari dan tidak melebihi jam di SPL
- PJK 1 : 1, saldo maksimal 9 jam; jadwal ambil PJK terlewat = hangus
"""

import datetime

import frappe
from frappe import _, bold
from frappe.utils import (
	add_days,
	cint,
	flt,
	get_datetime,
	getdate,
	now_datetime,
	nowdate,
	to_timedelta,
)

DOCTYPE = "Overtime Request"

MAKS_JAM_PER_HARI = 3
SALDO_PJK_MAKS = 9
MENIT_PEMBULATAN = 45
HARI_MINIMAL_SEBELUM = 0  # boleh diajukan di hari H (arahan Pak Ginanjar, 19 Nov 2026); tanggal lewat ditolak
HOLIDAY_LIST_TANGGAL_MERAH = "TANGGAL MERAH%"
FOTO_FIELD = {"mulai": "foto_mulai", "selesai": "foto_selesai"}

STATUS_AKTIF = ("Pending Supervisor", "Pending HR", "Approved", "In Progress", "Pending Confirmation", "Completed")
HR_MANAGER_ROLE = "HR Manager"
# Persetujuan tahap HRD hanya untuk role ini (diberikan ke orang HRD saja),
# bukan HR User / HR Manager yang juga dipegang IT, Admin GA, dsb.
HRD_ROLE = "HRD"


# ---------------------------------------------------------------------------
# Hitungan (fungsi murni, dites di hrms/xsha/test_lembur.py)
# ---------------------------------------------------------------------------


def _as_timedelta(value) -> datetime.timedelta:
	if isinstance(value, datetime.timedelta):
		return value
	if isinstance(value, datetime.time):
		return datetime.timedelta(hours=value.hour, minutes=value.minute, seconds=value.second)
	return to_timedelta(str(value))


def rentang_rencana(tanggal, jam_mulai, jam_selesai) -> tuple[datetime.datetime, datetime.datetime]:
	"""Datetime mulai dan selesai rencana. Jam selesai <= jam mulai berarti lewat tengah malam."""
	base = datetime.datetime.combine(getdate(tanggal), datetime.time())
	mulai = base + _as_timedelta(jam_mulai)
	selesai = base + _as_timedelta(jam_selesai)
	if selesai <= mulai:
		selesai += datetime.timedelta(days=1)
	return mulai, selesai


def durasi_jam(jam_mulai, jam_selesai) -> float:
	mulai, selesai = rentang_rencana("2000-01-01", jam_mulai, jam_selesai)
	return round((selesai - mulai).total_seconds() / 3600, 2)


def bulatkan_jam(menit: int) -> int:
	"""Jam penuh + 1 jika sisa >= 45 menit. Di bawah 45 menit total = 0."""
	menit = max(0, cint(menit))
	jam, sisa = divmod(menit, 60)
	return jam + (1 if sisa >= MENIT_PEMBULATAN else 0)


def hitung_jam_lembur(menit_nyata: int, jam_rencana: float) -> int:
	"""Jam yang diakui: dibulatkan, maksimal 3 jam dan tidak melebihi jam di SPL."""
	batas_spl = bulatkan_jam(round(flt(jam_rencana) * 60))
	return min(bulatkan_jam(menit_nyata), MAKS_JAM_PER_HARI, batas_spl)


def rentang_bertumpuk(a_mulai, a_selesai, b_mulai, b_selesai) -> bool:
	return a_mulai < b_selesai and b_mulai < a_selesai


# ---------------------------------------------------------------------------
# Helper data
# ---------------------------------------------------------------------------


def _is_hrd(user: str | None = None) -> bool:
	"""Orang HRD (role HRD): yang memproses tahap HRD lembur."""
	user = user or frappe.session.user
	return user == "Administrator" or HRD_ROLE in frappe.get_roles(user)


def _is_hr(user: str | None = None) -> bool:
	"""Akses umum HR (lihat semua lembur, bantu proses tahap atasan): role HR atau HRD."""
	from hrms.xsha.rules import _is_hr as is_hr

	return is_hr(user) or _is_hrd(user)


def _employee_user(employee: str) -> str | None:
	return frappe.db.get_value("Employee", employee, "user_id")


def _current_employee() -> str:
	from hrms.xsha.checkin import _current_employee as current

	return current()


def get_atasan(employee: str) -> str | None:
	"""Akun atasan: approver cuti karyawan, atau akun dari Reports To."""
	leave_approver, reports_to = frappe.db.get_value("Employee", employee, ["leave_approver", "reports_to"])
	if leave_approver:
		return leave_approver
	if reports_to:
		return _employee_user(reports_to)
	return None


def is_tanggal_merah(tanggal) -> bool:
	lists = frappe.get_all("Holiday List", filters={"name": ["like", HOLIDAY_LIST_TANGGAL_MERAH]}, pluck="name")
	if not lists:
		return False
	return bool(
		frappe.db.exists(
			"Holiday",
			{"parent": ["in", lists], "holiday_date": getdate(tanggal), "weekly_off": 0},
		)
	)


def get_saldo_pjk(employee: str, exclude: str | None = None) -> dict:
	"""Saldo PJK = jam lembur PJK yang sudah Selesai dan belum diambil.

	Rencana = jam PJK dari pengajuan yang sudah disetujui atasan tapi belum selesai,
	dipakai untuk mengecek batas 9 jam sebelum lembur berikutnya disetujui.
	"""
	filters = {"employee": employee, "kompensasi": "PJK"}
	if exclude:
		filters["name"] = ["!=", exclude]

	saldo = sum(
		cint(r.jam_dihitung)
		for r in frappe.get_all(
			DOCTYPE, filters={**filters, "status": "Completed", "status_pjk": "Not Taken"}, fields=["jam_dihitung"]
		)
	)
	rencana = sum(
		bulatkan_jam(round(flt(r.durasi_rencana) * 60))
		for r in frappe.get_all(
			DOCTYPE,
			filters={**filters, "status": ["in", ["Pending HR", "Approved", "In Progress", "Pending Confirmation"]]},
			fields=["durasi_rencana"],
		)
	)
	jadwal = frappe.get_all(
		DOCTYPE,
		filters={**filters, "status": "Completed", "status_pjk": "Not Taken"},
		fields=["name", "jam_dihitung", "pjk_tanggal", "pjk_jam_mulai", "pjk_jam_selesai"],
		order_by="pjk_tanggal asc",
	)
	return {"saldo": saldo, "rencana": rencana, "batas": SALDO_PJK_MAKS, "jadwal": jadwal}


def _notify(doc, to_user: str | None, message: str):
	if not to_user or to_user == frappe.session.user:
		return
	notification = frappe.new_doc("PWA Notification")
	notification.from_user = frappe.session.user
	notification.to_user = to_user
	notification.message = message
	notification.reference_document_type = DOCTYPE
	notification.reference_document_name = doc.name
	notification.insert(ignore_permissions=True)


def _hrd_users() -> list[str]:
	users = frappe.get_all(
		"Has Role",
		filters={"role": HRD_ROLE, "parenttype": "User"},
		pluck="parent",
		distinct=True,
	)
	return [u for u in users if u not in ("Administrator", "Guest") and frappe.db.get_value("User", u, "enabled")]


# ---------------------------------------------------------------------------
# Validasi dokumen (dipanggil dari controller Overtime Request)
# ---------------------------------------------------------------------------

FIELD_RENCANA = ("employee", "tanggal", "jam_mulai", "jam_selesai", "pekerjaan", "alasan")


def _nilai(value):
	"""Samakan bentuk nilai sebelum dibandingkan (jam dari aplikasi berupa teks, dari database timedelta)."""
	if value in (None, ""):
		return ""
	if isinstance(value, (datetime.timedelta, datetime.time)):
		td = _as_timedelta(value)
		return f"{int(td.total_seconds()) // 3600:02d}:{(int(td.total_seconds()) % 3600) // 60:02d}"
	if isinstance(value, (datetime.date, datetime.datetime)):
		return str(getdate(value))
	text = str(value).strip()
	if len(text) >= 5 and text[2] == ":" and text[:2].isdigit():
		return text[:5]
	return text


def validate(doc):
	if doc.jam_mulai and doc.jam_selesai:
		doc.durasi_rencana = durasi_jam(doc.jam_mulai, doc.jam_selesai)

	if doc.is_new():
		doc.status = "Pending Supervisor"
		doc.atasan = get_atasan(doc.employee)
		_validate_pemilik(doc)
		_validate_rencana(doc)
		return

	before = doc.get_doc_before_save()
	if not before:
		return

	aksi = doc.flags.get("lembur_aksi")
	if doc.status != before.status and not aksi and not _is_hr():
		frappe.throw(_("Overtime Request status can only be changed through the approval actions."))

	rencana_berubah = any(_nilai(doc.get(f)) != _nilai(before.get(f)) for f in FIELD_RENCANA)
	if rencana_berubah:
		if before.status != "Pending Supervisor" and not _is_hr():
			frappe.throw(_("This request has already been processed and cannot be edited. Cancel it and create a new one."))
		if doc.employee != before.employee and not _is_hr():
			frappe.throw(_("The employee on this request cannot be changed."))
		_validate_rencana(doc)


def _validate_pemilik(doc):
	"""Karyawan hanya boleh mengajukan untuk dirinya sendiri. HR boleh atas nama karyawan lain."""
	if _is_hr() or frappe.flags.in_import or frappe.flags.in_patch:
		return
	if _employee_user(doc.employee) != frappe.session.user:
		frappe.throw(_("You can only request overtime for yourself."))


def _validate_rencana(doc):
	durasi = flt(doc.durasi_rencana)
	if durasi <= 0:
		frappe.throw(_("To Time must be after From Time."))
	if durasi > MAKS_JAM_PER_HARI:
		frappe.throw(
			_("Overtime is limited to {0} hours per day. You planned {1} hours.").format(MAKS_JAM_PER_HARI, durasi)
		)
	if bulatkan_jam(round(durasi * 60)) < 1:
		frappe.throw(_("Overtime must be at least 1 hour (less than 45 minutes is not counted)."))

	if not _is_hr():
		batas = add_days(getdate(nowdate()), HARI_MINIMAL_SEBELUM)
		if getdate(doc.tanggal) < batas:
			frappe.throw(
				_("Overtime date {0} has already passed. Please contact HR.").format(
					frappe.format(doc.tanggal, "Date")
				)
				if HARI_MINIMAL_SEBELUM == 0
				else _("Overtime must be requested at least {0} day(s) before. For {1}, please contact HR.").format(
					HARI_MINIMAL_SEBELUM, frappe.format(doc.tanggal, "Date")
				),
				title=_("Request Too Late"),
			)

	mulai, selesai = rentang_rencana(doc.tanggal, doc.jam_mulai, doc.jam_selesai)
	lain = frappe.get_all(
		DOCTYPE,
		filters={
			"employee": doc.employee,
			"name": ["!=", doc.name or ""],
			"status": ["in", STATUS_AKTIF],
			"tanggal": ["between", [add_days(doc.tanggal, -1), add_days(doc.tanggal, 1)]],
		},
		fields=["name", "tanggal", "jam_mulai", "jam_selesai"],
	)
	for r in lain:
		m, s = rentang_rencana(r.tanggal, r.jam_mulai, r.jam_selesai)
		if rentang_bertumpuk(mulai, selesai, m, s):
			frappe.throw(_("Overtime hours overlap with request {0}.").format(bold(r.name)))

	jam_hari_itu = sum(
		flt(r.durasi_rencana)
		for r in frappe.get_all(
			DOCTYPE,
			filters={
				"employee": doc.employee,
				"name": ["!=", doc.name or ""],
				"status": ["in", STATUS_AKTIF],
				"tanggal": doc.tanggal,
			},
			fields=["durasi_rencana"],
		)
	)
	if jam_hari_itu + durasi > MAKS_JAM_PER_HARI:
		frappe.throw(
			_("Total overtime on this date would be {0} hours, above the {1} hours daily limit.").format(
				jam_hari_itu + durasi, MAKS_JAM_PER_HARI
			)
		)


def after_insert(doc):
	_notify(
		doc,
		doc.atasan,
		f"{bold(doc.employee_name)} raised a new {bold('Overtime Request')} for {frappe.format(doc.tanggal, 'Date')}: {doc.name}",
	)


# ---------------------------------------------------------------------------
# Hak akses (has_permission / permission_query_conditions di hooks)
# ---------------------------------------------------------------------------


def has_permission(doc, ptype=None, user=None):
	user = user or frappe.session.user
	if user == "Administrator" or _is_hr(user) or "System Manager" in frappe.get_roles(user):
		return True
	if doc.atasan == user or _employee_user(doc.employee) == user:
		if ptype in ("write", "delete", "cancel", "submit") and _employee_user(doc.employee) != user:
			return False
		return True
	return False


def get_permission_query_conditions(user=None):
	user = user or frappe.session.user
	if user == "Administrator" or _is_hr(user) or "System Manager" in frappe.get_roles(user):
		return ""
	user_esc = frappe.db.escape(user)
	employees = frappe.get_all("Employee", filters={"user_id": user}, pluck="name")
	conditions = [f"`tab{DOCTYPE}`.`atasan` = {user_esc}"]
	if employees:
		conditions.append(
			f"`tab{DOCTYPE}`.`employee` in ({', '.join(frappe.db.escape(e) for e in employees)})"
		)
	return "(" + " or ".join(conditions) + ")"


# ---------------------------------------------------------------------------
# Aksi (dipanggil dari aplikasi HRMS)
# ---------------------------------------------------------------------------


def _ambil(name: str, status_boleh: tuple[str, ...]):
	doc = frappe.get_doc(DOCTYPE, name)
	if doc.status not in status_boleh:
		frappe.throw(
			_("Request {0} is {1}, this action is not allowed.").format(bold(doc.name), bold(_(doc.status)))
		)
	return doc


def _simpan(doc, aksi: str):
	doc.flags.lembur_aksi = aksi
	doc.flags.ignore_permissions = True
	doc.save()
	return doc.as_dict()


def _bukan_pemohon(doc, label: str):
	user = frappe.session.user
	if user != "Administrator" and _employee_user(doc.employee) == user:
		frappe.throw(_("You cannot {0} your own Overtime Request.").format(label))


def _wajib_atasan(doc):
	user = frappe.session.user
	if user != doc.atasan and not _is_hr(user):
		frappe.throw(
			_("Only the supervisor ({0}) or HR can process this request.").format(bold(doc.atasan or "-")),
			title=_("Not the Supervisor"),
		)


def _boleh_tahap_hrd(doc, user: str | None = None) -> bool:
	"""Tahap HRD: semua role HRD (bukan orang tertentu). Kalau tidak ada HRD lain selain pemohon
	(mis. lembur milik satu-satunya HRD), atasan pemohon yang memproses supaya tidak macet."""
	from hrms.xsha.approval import supervisor_is_final

	user = user or frappe.session.user
	if _is_hrd(user):
		return True
	return bool(doc.atasan) and user == doc.atasan and supervisor_is_final(doc.employee)


def _wajib_hrd(doc):
	if not _boleh_tahap_hrd(doc):
		frappe.throw(_("Only HRD can process this step."), title=_("Not HRD"))


@frappe.whitelist(methods=["POST"])
def setujui_atasan(name: str, kompensasi: str, pjk_tanggal=None, pjk_jam_mulai=None, pjk_jam_selesai=None):
	doc = _ambil(name, ("Pending Supervisor",))
	_bukan_pemohon(doc, _("approve"))
	_wajib_atasan(doc)

	if kompensasi not in ("PJK", "Paid Overtime"):
		frappe.throw(_("Select compensation: PJK or Paid Overtime."))
	doc.kompensasi = kompensasi
	doc.pjk_tanggal = doc.pjk_jam_mulai = doc.pjk_jam_selesai = None
	doc.saldo_pjk_penuh = 0

	if kompensasi == "PJK":
		if not (pjk_tanggal and pjk_jam_mulai and pjk_jam_selesai):
			frappe.throw(_("For PJK, enter the PJK date and time."))
		if getdate(pjk_tanggal) <= getdate(doc.tanggal):
			frappe.throw(_("PJK Date must be after the overtime date."))
		if durasi_jam(pjk_jam_mulai, pjk_jam_selesai) <= 0:
			frappe.throw(_("PJK To Time must be after From Time."))
		doc.pjk_tanggal, doc.pjk_jam_mulai, doc.pjk_jam_selesai = pjk_tanggal, pjk_jam_mulai, pjk_jam_selesai
		saldo = get_saldo_pjk(doc.employee, exclude=doc.name)
		jam_baru = bulatkan_jam(round(flt(doc.durasi_rencana) * 60))
		doc.saldo_pjk_penuh = cint(saldo["saldo"] + saldo["rencana"] + jam_baru > SALDO_PJK_MAKS)

	doc.status = "Pending HR"
	doc.disetujui_atasan_oleh = frappe.session.user
	doc.disetujui_atasan_pada = now_datetime()
	hasil = _simpan(doc, "setujui_atasan")
	from hrms.xsha.approval import final_approver_users

	for hrd in final_approver_users(doc.employee, None):
		_notify(doc, hrd, f"{bold('Overtime Request')} {doc.name} of {bold(doc.employee_name)} was approved by the supervisor and is waiting for HR")
	return hasil


@frappe.whitelist(methods=["POST"])
def setujui_hrd(name: str, ubah_ke_berbayar: int = 0):
	doc = _ambil(name, ("Pending HR",))
	_bukan_pemohon(doc, _("approve"))
	_wajib_hrd(doc)

	if cint(ubah_ke_berbayar):
		if not _boleh_tahap_hrd(doc):
			frappe.throw(_("Only HRD can change PJK to Paid Overtime."))
		doc.kompensasi = "Paid Overtime"
		doc.pjk_tanggal = doc.pjk_jam_mulai = doc.pjk_jam_selesai = None
		doc.saldo_pjk_penuh = 0
	elif doc.kompensasi == "PJK" and doc.saldo_pjk_penuh:
		frappe.throw(
			_(
				"This employee's PJK balance would exceed {0} hours. Reject the request, or HRD can approve it as Paid Overtime."
			).format(SALDO_PJK_MAKS),
			title=_("PJK Balance Exceeded"),
		)

	doc.status = "Approved"
	doc.disetujui_hrd_oleh = frappe.session.user
	doc.disetujui_hrd_pada = now_datetime()
	doc.nomor_spl = "SPL-" + doc.name.split("-", 1)[-1]
	hasil = _simpan(doc, "setujui_hrd")
	pesan = f"{bold('Overtime Request')} {doc.name} ({frappe.format(doc.tanggal, 'Date')}) has been {bold('Approved')}. SPL number {doc.nomor_spl}"
	_notify(doc, _employee_user(doc.employee), pesan)
	_notify(doc, doc.atasan, f"{bold(doc.employee_name)}: {pesan}")
	return hasil


@frappe.whitelist(methods=["POST"])
def tolak(name: str, alasan: str):
	doc = _ambil(name, ("Pending Supervisor", "Pending HR"))
	_bukan_pemohon(doc, _("reject"))
	if doc.status == "Pending Supervisor":
		_wajib_atasan(doc)
	else:
		_wajib_hrd(doc)
	if not (alasan or "").strip():
		frappe.throw(_("Please enter a rejection reason."))

	doc.status = "Rejected"
	doc.alasan_penolakan = alasan.strip()
	hasil = _simpan(doc, "tolak")
	pesan = f"{bold('Overtime Request')} {doc.name} ({frappe.format(doc.tanggal, 'Date')}) has been {bold('Rejected')}: {frappe.utils.escape_html(doc.alasan_penolakan)}"
	_notify(doc, _employee_user(doc.employee), pesan)
	_notify(doc, doc.atasan, f"{bold(doc.employee_name)}: {pesan}")
	return hasil


@frappe.whitelist(methods=["POST"])
def batalkan(name: str):
	doc = _ambil(name, ("Pending Supervisor", "Pending HR", "Approved"))
	if _employee_user(doc.employee) != frappe.session.user and not _is_hr():
		frappe.throw(_("Only the employee or HR can cancel this request."))
	doc.status = "Cancelled"
	hasil = _simpan(doc, "batalkan")
	_notify(doc, doc.atasan, f"{bold(doc.employee_name)} cancelled {bold('Overtime Request')} {doc.name}")
	return hasil


def _simpan_foto(doc, jenis: str, photo: str | None):
	from hrms.xsha.checkin import decode_photo, validate_photo

	if not photo:
		frappe.throw(_("A selfie is required."))
	content = decode_photo(photo)
	validate_photo(content)
	stamp = now_datetime().strftime("%Y%m%d-%H%M%S")
	file_doc = frappe.get_doc(
		{
			"doctype": "File",
			"file_name": f"lembur_{jenis}_{doc.employee}_{stamp}_{frappe.generate_hash(length=6)}.jpg",
			"is_private": 1,
			"content": content,
			"attached_to_doctype": DOCTYPE,
			"attached_to_name": doc.name,
			"attached_to_field": FOTO_FIELD[jenis],
		}
	)
	file_doc.flags.ignore_permissions = True
	file_doc.insert()
	return file_doc.file_url


def _cek_lokasi(latitude, longitude):
	if frappe.db.get_single_value("HR Settings", "allow_geolocation_tracking") and not (latitude or longitude):
		frappe.throw(_("Location is required to record overtime."))


@frappe.whitelist(methods=["POST"])
def mulai_lembur(name: str, latitude=None, longitude=None, photo: str | None = None):
	return catat_mulai(name, now_datetime(), latitude, longitude, photo)


def catat_mulai(name: str, sekarang, latitude=None, longitude=None, photo=None, offline_id=None):
	"""sekarang = jam server, atau jam HP terkoreksi untuk data offline (hrms.xsha.offline)."""
	doc = _ambil(name, ("Approved",))
	if _employee_user(doc.employee) != frappe.session.user:
		frappe.throw(_("Only the employee can start this overtime."))
	mulai, selesai = rentang_rencana(doc.tanggal, doc.jam_mulai, doc.jam_selesai)
	if not (mulai - datetime.timedelta(minutes=30) <= sekarang <= selesai):
		frappe.throw(
			_("Overtime can only be started within the SPL schedule ({0} to {1}).").format(
				mulai.strftime("%d-%m-%Y %H:%M"), selesai.strftime("%H:%M")
			)
		)
	_cek_lokasi(latitude, longitude)
	doc.foto_mulai = _simpan_foto(doc, "mulai", photo)
	doc.mulai_lembur = sekarang
	doc.mulai_latitude, doc.mulai_longitude = flt(latitude), flt(longitude)
	if offline_id:
		doc.mulai_offline, doc.mulai_offline_id = 1, offline_id
	doc.status = "In Progress"
	return _simpan(doc, "mulai")


def _isi_realisasi(doc, selesai: datetime.datetime):
	menit = int((get_datetime(selesai) - get_datetime(doc.mulai_lembur)).total_seconds() // 60)
	if menit < 0:
		frappe.throw(_("End time cannot be before the overtime start time."))
	doc.selesai_lembur = selesai
	doc.menit_realisasi = menit
	doc.jam_dihitung = hitung_jam_lembur(menit, doc.durasi_rencana)
	doc.tanggal_merah = cint(is_tanggal_merah(doc.tanggal))


@frappe.whitelist(methods=["POST"])
def selesai_lembur(name: str, latitude=None, longitude=None, photo: str | None = None):
	return catat_selesai(name, now_datetime(), latitude, longitude, photo)


def catat_selesai(name: str, sekarang, latitude=None, longitude=None, photo=None, offline_id=None):
	doc = _ambil(name, ("In Progress",))
	if _employee_user(doc.employee) != frappe.session.user:
		frappe.throw(_("Only the employee can end this overtime."))
	_cek_lokasi(latitude, longitude)
	doc.foto_selesai = _simpan_foto(doc, "selesai", photo)
	doc.selesai_latitude, doc.selesai_longitude = flt(latitude), flt(longitude)
	if offline_id:
		doc.selesai_offline, doc.selesai_offline_id = 1, offline_id
	_isi_realisasi(doc, sekarang)
	doc.status = "Pending Confirmation"
	hasil = _simpan(doc, "selesai")
	_notify(
		doc,
		doc.atasan,
		f"{bold(doc.employee_name)} ended overtime {doc.name} ({doc.jam_dihitung} hours). Please confirm",
	)
	return hasil


@frappe.whitelist(methods=["POST"])
def konfirmasi(name: str, jam_selesai_manual=None):
	"""Atasan/HRD mengonfirmasi realisasi. Jika karyawan lupa menekan Selesai, isi jam selesai manual."""
	doc = _ambil(name, ("Pending Confirmation", "In Progress"))
	_bukan_pemohon(doc, _("confirm"))
	_wajib_atasan(doc)

	if doc.status == "In Progress":
		if not jam_selesai_manual:
			frappe.throw(_("The employee has not ended the overtime. Enter the end time."))
		selesai = datetime.datetime.combine(getdate(doc.mulai_lembur), datetime.time()) + _as_timedelta(
			jam_selesai_manual
		)
		if selesai <= get_datetime(doc.mulai_lembur):
			selesai += datetime.timedelta(days=1)
		_isi_realisasi(doc, selesai)
		doc.selesai_diisi_manual = 1

	doc.status = "Completed"
	doc.dikonfirmasi_oleh = frappe.session.user
	doc.dikonfirmasi_pada = now_datetime()
	if doc.kompensasi == "PJK" and cint(doc.jam_dihitung) > 0:
		doc.status_pjk = "Not Taken"
	hasil = _simpan(doc, "konfirmasi")
	pesan = f"{bold('Overtime Request')} {doc.name} confirmed: {doc.jam_dihitung} hours ({_(doc.kompensasi)})"
	_notify(doc, _employee_user(doc.employee), pesan)
	return hasil


# ---------------------------------------------------------------------------
# Data untuk aplikasi
# ---------------------------------------------------------------------------

LIST_FIELDS = [
	"name",
	"employee",
	"employee_name",
	"tanggal",
	"jam_mulai",
	"jam_selesai",
	"durasi_rencana",
	"pekerjaan",
	"status",
	"kompensasi",
	"atasan",
	"jam_dihitung",
	"status_pjk",
	"nomor_spl",
	"creation",
]


@frappe.whitelist()
def get_lembur_list(employee: str | None = None, for_approval: int = 0, limit: int | None = 10) -> list[dict]:
	user = frappe.session.user
	if cint(for_approval):
		or_filters = [
			["atasan", "=", user],
		]
		filters = {"status": ["in", ["Pending Supervisor", "Pending Confirmation", "In Progress"]]}
		rows = frappe.get_all(
			DOCTYPE, filters=filters, or_filters=or_filters, fields=LIST_FIELDS, order_by="creation desc", limit=limit
		)
		if _is_hrd(user):
			rows += frappe.get_all(
				DOCTYPE, filters={"status": "Pending HR"}, fields=LIST_FIELDS, order_by="creation desc", limit=limit
			)
		else:
			# tahap HRD tanpa HRD lain (mis. lembur milik satu-satunya HRD): atasan yang memproses
			from hrms.xsha.approval import supervisor_is_final

			rows += [
				r
				for r in frappe.get_all(
					DOCTYPE, filters={"status": "Pending HR", "atasan": user}, fields=LIST_FIELDS, order_by="creation desc"
				)
				if supervisor_is_final(r.employee)
			]
		own = set(frappe.get_all("Employee", filters={"user_id": user}, pluck="name"))
		seen, hasil = set(), []
		for r in sorted(rows, key=lambda x: x.creation, reverse=True):
			if r.name in seen or r.employee in own:
				continue
			seen.add(r.name)
			hasil.append(r)
		return hasil[: cint(limit)] if limit else hasil

	employee = employee or _current_employee()
	if _employee_user(employee) != user and not _is_hr(user):
		frappe.throw(_("Not permitted."), frappe.PermissionError)
	return frappe.get_all(
		DOCTYPE, filters={"employee": employee}, fields=LIST_FIELDS, order_by="tanggal desc, creation desc", limit=limit
	)


@frappe.whitelist()
def get_lembur_hari_ini() -> list[dict]:
	"""SPL milik karyawan yang bisa dimulai/diselesaikan sekarang (untuk panel di Home)."""
	employee = frappe.db.get_value("Employee", {"user_id": frappe.session.user, "status": "Active"}, "name")
	if not employee:
		return []
	hari_ini = getdate(nowdate())
	rows = frappe.get_all(
		DOCTYPE,
		filters={
			"employee": employee,
			"status": ["in", ["Approved", "In Progress"]],
			"tanggal": ["between", [add_days(hari_ini, -1), hari_ini]],
		},
		fields=LIST_FIELDS + ["mulai_lembur"],
		order_by="tanggal asc, jam_mulai asc",
	)
	sekarang = now_datetime()
	hasil = []
	for r in rows:
		mulai, selesai = rentang_rencana(r.tanggal, r.jam_mulai, r.jam_selesai)
		if r.status == "In Progress" or (mulai - datetime.timedelta(minutes=30) <= sekarang <= selesai):
			r.rencana_mulai, r.rencana_selesai = mulai, selesai
			hasil.append(r)
	return hasil


@frappe.whitelist()
def get_saldo_pjk_saya() -> dict:
	employee = frappe.db.get_value("Employee", {"user_id": frappe.session.user, "status": "Active"}, "name")
	if not employee:
		return {"saldo": 0, "rencana": 0, "batas": SALDO_PJK_MAKS, "jadwal": []}
	return get_saldo_pjk(employee)


@frappe.whitelist()
def get_info_persetujuan(name: str) -> dict:
	"""Tombol apa yang boleh ditampilkan aplikasi untuk user ini pada pengajuan ini."""
	doc = frappe.get_doc(DOCTYPE, name)
	doc.check_permission("read")
	user = frappe.session.user
	pemohon = _employee_user(doc.employee) == user
	atasan_atau_hr = (user == doc.atasan or _is_hr(user)) and not pemohon
	hr = _boleh_tahap_hrd(doc, user) and not pemohon
	return {
		"bisa_setujui_atasan": doc.status == "Pending Supervisor" and atasan_atau_hr,
		"bisa_setujui_hrd": doc.status == "Pending HR" and hr,
		"bisa_ubah_ke_berbayar": doc.status == "Pending HR" and hr,
		"bisa_tolak": (doc.status == "Pending Supervisor" and atasan_atau_hr) or (doc.status == "Pending HR" and hr),
		"bisa_konfirmasi": doc.status in ("Pending Confirmation", "In Progress") and atasan_atau_hr,
		"bisa_batalkan": doc.status in ("Pending Supervisor", "Pending HR", "Approved") and (pemohon or _is_hr(user)),
		"saldo_pjk": get_saldo_pjk(doc.employee, exclude=doc.name) if atasan_atau_hr else None,
	}


# ---------------------------------------------------------------------------
# Scheduler dan kait ke Attendance
# ---------------------------------------------------------------------------


def hanguskan_pjk():
	"""Harian: PJK yang jadwal ambilnya sudah lewat dan belum diambil menjadi Expired."""
	for name in frappe.get_all(
		DOCTYPE,
		filters={"status_pjk": "Not Taken", "pjk_tanggal": ["<", nowdate()]},
		pluck="name",
	):
		frappe.db.set_value(DOCTYPE, name, "status_pjk", "Expired")


def _pjk_hari_itu(employee: str, tanggal):
	# Jangan pernah menggagalkan Auto Attendance: lewati jika tabel lembur belum ada (belum migrate).
	if not frappe.db.table_exists(DOCTYPE):
		return []
	return frappe.get_all(
		DOCTYPE,
		filters={"employee": employee, "status_pjk": "Not Taken", "pjk_tanggal": getdate(tanggal)},
		fields=["name", "jam_dihitung", "pjk_jam_mulai", "pjk_jam_selesai"],
	)


def _pjk_di_awal_shift(p, shift_start, shift_end) -> bool:
	"""PJK di awal shift (boleh datang lebih siang) bila jam mulainya sebelum tengah shift.

	PJK lama tanpa jam mulai dianggap di akhir shift (pulang lebih awal), seperti aturan sebelumnya.
	"""
	if not p.pjk_jam_mulai:
		return False
	mulai = datetime.datetime.combine(shift_start.date(), datetime.time()) + _as_timedelta(p.pjk_jam_mulai)
	if mulai < shift_start - datetime.timedelta(hours=12):
		mulai += datetime.timedelta(days=1)  # shift malam: PJK setelah tengah malam
	return mulai < shift_start + (shift_end - shift_start) / 2


def _rentang_shift(shift_type: str, tanggal):
	"""(mulai, selesai, toleransi telat, toleransi pulang cepat) shift pada tanggal itu, atau None."""
	row = frappe.db.get_value(
		"Shift Type", shift_type, ["start_time", "end_time", "late_entry_grace_period", "early_exit_grace_period"]
	)
	if not row or row[0] is None or row[1] is None:
		return None
	base = datetime.datetime.combine(getdate(tanggal), datetime.time())
	shift_start = base + _as_timedelta(row[0])
	shift_end = base + _as_timedelta(row[1])
	if shift_end <= shift_start:
		shift_end += datetime.timedelta(days=1)  # shift melewati tengah malam
	return shift_start, shift_end, cint(row[2]), cint(row[3])


def menit_pjk_awal(employee: str, tanggal, shift_type: str) -> int:
	"""Jatah datang lebih siang (menit) dari PJK awal shift yang belum diambil. Dipakai HR Dashboard."""
	if not (employee and tanggal and shift_type):
		return 0
	pjk = _pjk_hari_itu(employee, tanggal)
	shift = _rentang_shift(shift_type, tanggal) if pjk else None
	if not shift:
		return 0
	return 60 * sum(cint(p.jam_dihitung) for p in pjk if _pjk_di_awal_shift(p, shift[0], shift[1]))


def attendance_before_submit(doc, method=None):
	"""PJK lembur dipakai di hari absensi dan PJK tercatat diambil.

	- PJK di awal shift: datang terlambat sampai jatah jam PJK (+ toleransi telat) tidak dihitung telat.
	- PJK di akhir shift: pulang lebih awal dalam jatah jam PJK (- toleransi) tidak dihitung pulang cepat.
	Datang/pulang normal (PJK tidak dipakai) tidak mengubah apa pun; PJK hangus esok harinya.
	"""
	if not doc.employee or not doc.attendance_date or not doc.shift:
		return
	pjk = _pjk_hari_itu(doc.employee, doc.attendance_date)
	if not pjk:
		return

	shift = _rentang_shift(doc.shift, doc.attendance_date)
	if not shift:
		return
	shift_start, shift_end, grace_masuk, grace_pulang = shift

	awal = [p for p in pjk if _pjk_di_awal_shift(p, shift_start, shift_end)]
	akhir = [p for p in pjk if p not in awal]
	diambil = []

	# Datang lebih siang dalam jatah PJK awal shift: tidak dihitung telat.
	if awal and doc.in_time:
		in_time = get_datetime(doc.in_time)
		toleransi = datetime.timedelta(minutes=cint(grace_masuk))
		jam = sum(cint(p.jam_dihitung) for p in awal)
		if shift_start + toleransi < in_time <= shift_start + datetime.timedelta(hours=jam) + toleransi:
			doc.late_entry = 0
			diambil += [p.name for p in awal]

	# Pulang lebih awal dalam jatah PJK akhir shift: tidak dihitung pulang cepat.
	if akhir and doc.out_time:
		out_time = get_datetime(doc.out_time)
		toleransi = datetime.timedelta(minutes=cint(grace_pulang))
		jam = sum(cint(p.jam_dihitung) for p in akhir)
		if shift_end - datetime.timedelta(hours=jam) - toleransi <= out_time < shift_end - toleransi:
			doc.early_exit = 0
			diambil += [p.name for p in akhir]

	if diambil:
		doc.flags.xsha_pjk = diambil


def attendance_on_submit(doc, method=None):
	for name in doc.flags.get("xsha_pjk") or []:
		frappe.db.set_value(
			DOCTYPE, name, {"status_pjk": "Taken", "pjk_diambil_pada": doc.attendance_date}, update_modified=False
		)
