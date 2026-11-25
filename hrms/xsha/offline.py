"""Mode offline aplikasi X-PEOPLE.

Saat server tidak bisa dihubungi (down, 5xx, timeout), aplikasi menyimpan check-in/out
dan Mulai/Selesai Lembur di HP (IndexedDB), lalu mengirimnya otomatis lewat endpoint di
file ini begitu server bisa dihubungi lagi. Lihat frontend/src/offline/.

Aturan jam (keputusan Lutpi, 21 Nov 2026):
- jam yang dipakai = jam HP + selisih jam HP vs server yang dicatat aplikasi terakhir kali
  online (dikirim sebagai epoch ms UTC, jadi zona waktu HP tidak berpengaruh)
- data ditandai offline (custom_offline / mulai_offline / selesai_offline) untuk audit HRD
- data yang lebih tua dari BATAS_UMUR_JAM atau jamnya di masa depan ditolak

Jika check-in offline baru masuk setelah Attendance hari itu dibuat otomatis, Attendance
tersebut dibatalkan lalu dihitung ulang (perbaiki_attendance). Attendance buatan HR tidak
disentuh; HRD diberi notifikasi.
"""

import datetime

import frappe
from frappe import _
from frappe.utils import cint, get_datetime, getdate, now_datetime
from frappe.utils.data import convert_utc_to_system_timezone

BATAS_UMUR_JAM = 24
TOLERANSI_MASA_DEPAN = datetime.timedelta(minutes=2)
# Check-in yang sebenarnya sudah tersimpan saat dikirim langsung (respons hilang/timeout)
# lalu ikut terkirim lagi dari antrean: dianggap sama jika jenis sama dan jamnya berdekatan.
JENDELA_DUPLIKAT = (datetime.timedelta(minutes=1), datetime.timedelta(minutes=3))

STATUS_ATTENDANCE_OTOMATIS = ("Present", "Absent", "Half Day")


def waktu_dari_hp(waktu_ms) -> datetime.datetime:
	"""Epoch ms (UTC) dari HP -> datetime naive zona waktu sistem, dengan validasi umur."""
	try:
		ms = int(waktu_ms)
	except (TypeError, ValueError):
		frappe.throw(_("Jam data offline tidak valid."))

	utc = datetime.datetime.fromtimestamp(ms / 1000, tz=datetime.timezone.utc)
	waktu = convert_utc_to_system_timezone(utc).replace(tzinfo=None, microsecond=0)
	sekarang = now_datetime().replace(microsecond=0)

	if waktu > sekarang + TOLERANSI_MASA_DEPAN:
		frappe.throw(
			_("Jam data offline ({0}) lebih maju dari jam server. Periksa pengaturan jam di HP.").format(
				waktu.strftime("%d-%m-%Y %H:%M")
			),
			title=_("Jam Tidak Valid"),
		)
	if waktu < sekarang - datetime.timedelta(hours=BATAS_UMUR_JAM):
		frappe.throw(
			_(
				"Data offline tanggal {0} sudah lebih dari {1} jam sehingga tidak bisa dikirim otomatis. "
				"Ajukan koreksi lewat Attendance Request atau hubungi HR."
			).format(waktu.strftime("%d-%m-%Y %H:%M"), BATAS_UMUR_JAM),
			title=_("Data Offline Kedaluwarsa"),
		)
	return min(waktu, sekarang)


def _offline_id(offline_id) -> str:
	offline_id = (offline_id or "").strip()
	if not offline_id or len(offline_id) > 64:
		frappe.throw(_("ID data offline tidak valid."))
	return offline_id


def _hasil_checkin(row) -> dict:
	return {
		"name": row.name,
		"log_type": row.log_type,
		"time": row.time,
		"shift": row.shift,
		"offshift": cint(row.offshift),
		"offline": 1,
	}


# ---------------------------------------------------------------------------
# Check-in / check-out
# ---------------------------------------------------------------------------


@frappe.whitelist(methods=["POST"])
def sync_checkin(
	offline_id: str, log_type: str, waktu_ms, latitude=None, longitude=None, photo: str | None = None
) -> dict:
	from hrms.xsha.checkin import _current_employee, buat_checkin

	offline_id = _offline_id(offline_id)
	if log_type not in ("IN", "OUT"):
		frappe.throw(_("Jenis log tidak valid."))

	fields = ["name", "log_type", "time", "shift", "offshift"]
	if frappe.get_meta("Employee Checkin").has_field("custom_offline_id"):
		if sudah := frappe.db.get_value("Employee Checkin", {"custom_offline_id": offline_id}, fields, as_dict=True):
			return _hasil_checkin(sudah)  # pengiriman ulang dari antrean

	waktu = waktu_dari_hp(waktu_ms)
	employee = _current_employee()

	sebelum, sesudah = JENDELA_DUPLIKAT
	if sama := frappe.db.get_value(
		"Employee Checkin",
		{"employee": employee, "log_type": log_type, "time": ["between", [waktu - sebelum, waktu + sesudah]]},
		fields,
		as_dict=True,
	):
		return _hasil_checkin(sama)

	hasil = buat_checkin(log_type, latitude, longitude, photo, waktu_offline=waktu, offline_id=offline_id)
	frappe.enqueue(
		"hrms.xsha.offline.perbaiki_attendance",
		checkin=hasil["name"],
		queue="short",
		enqueue_after_commit=True,
	)
	hasil["offline"] = 1
	return hasil


# ---------------------------------------------------------------------------
# Mulai / Selesai Lembur
# ---------------------------------------------------------------------------


@frappe.whitelist(methods=["POST"])
def sync_lembur(
	offline_id: str, aksi: str, name: str, waktu_ms, latitude=None, longitude=None, photo: str | None = None
) -> dict:
	from hrms.xsha import lembur

	offline_id = _offline_id(offline_id)
	if aksi not in ("mulai", "selesai"):
		frappe.throw(_("Aksi lembur tidak valid."))

	doc = frappe.get_doc(lembur.DOCTYPE, name)
	if lembur._employee_user(doc.employee) != frappe.session.user:
		frappe.throw(_("Not permitted."), frappe.PermissionError)

	# Sudah tercatat: pengiriman ulang dari antrean, atau kiriman langsung yang sebenarnya
	# berhasil tapi responsnya tidak sampai ke HP.
	if doc.get(f"{aksi}_offline_id") == offline_id:
		return doc.as_dict()
	if aksi == "mulai" and doc.mulai_lembur and doc.status in ("In Progress", "Pending Confirmation", "Completed"):
		return doc.as_dict()
	if aksi == "selesai" and doc.status in ("Pending Confirmation", "Completed"):
		return doc.as_dict()

	waktu = waktu_dari_hp(waktu_ms)
	if aksi == "mulai":
		return lembur.catat_mulai(name, waktu, latitude, longitude, photo, offline_id=offline_id)
	return lembur.catat_selesai(name, waktu, latitude, longitude, photo, offline_id=offline_id)


# ---------------------------------------------------------------------------
# Attendance yang sudah dibuat sebelum check-in offline masuk
# ---------------------------------------------------------------------------


def perbaiki_attendance(checkin: str):
	"""Background job setelah check-in offline tersimpan."""
	pengguna = frappe.session.user
	# Attendance hasil hitung ulang dibuat atas nama Administrator, sama seperti jadwal
	# auto attendance, supaya tetap dikenali sebagai Attendance otomatis.
	frappe.set_user("Administrator")
	try:
		_perbaiki(checkin)
	except Exception:
		frappe.db.rollback()
		frappe.log_error(title=f"X-PEOPLE offline: perbaiki attendance {checkin}")
	finally:
		frappe.set_user(pengguna)


def _perbaiki(checkin: str):
	log = frappe.db.get_value(
		"Employee Checkin",
		checkin,
		["name", "employee", "employee_name", "log_type", "time", "shift", "shift_start", "shift_actual_end", "offshift", "attendance", "device_id"],
		as_dict=True,
	)
	if not log or not log.shift or not log.shift_start or cint(log.offshift) or log.attendance:
		return

	from hrms.xsha.auto_checkout import DEVICE_ID, hapus_auto_checkout

	checkout_asli = log.log_type == "OUT" and log.device_id != DEVICE_ID
	if checkout_asli:
		# check-out asli menggantikan check-out otomatis di shift yang sama
		hapus_auto_checkout(log.employee, log.shift, log.shift_start, kecuali=log.name)

	shift = frappe.get_doc("Shift Type", log.shift)
	if not cint(shift.enable_auto_attendance) or not shift.last_sync_of_checkin or not shift.process_attendance_after:
		return
	if get_datetime(log.time) < get_datetime(shift.process_attendance_after):
		return
	if get_datetime(log.shift_actual_end) >= get_datetime(shift.last_sync_of_checkin):
		return  # shift ini belum diproses; jadwal auto attendance biasa yang akan menghitungnya

	tanggal = getdate(log.shift_start)
	attendance = frappe.get_all(
		"Attendance",
		filters={"employee": log.employee, "attendance_date": tanggal, "docstatus": 1},
		fields=["name", "owner", "status", "attendance_request", "leave_application"],
		limit=1,
	)
	if not attendance:
		_hitung_ulang(shift, log.employee, log.shift_start)
		return

	lama = attendance[0]
	if not _attendance_otomatis(lama):
		_kabari_hrd(
			log,
			_(
				"Check-in offline {0} ({1} {2}) baru terkirim setelah Attendance {3} dibuat manual. "
				"Attendance tidak diubah otomatis, mohon dicek."
			).format(frappe.bold(log.employee_name), log.log_type, log.time, lama.name),
		)
		return

	doc = frappe.get_doc("Attendance", lama.name)
	doc.flags.ignore_permissions = True
	doc.cancel()
	if checkout_asli:
		hapus_auto_checkout(log.employee, log.shift, log.shift_start, kecuali=log.name)
	doc.add_comment(
		"Comment",
		_("Dibatalkan otomatis: check-in offline {0} ({1} {2}) baru terkirim, Attendance dihitung ulang.").format(
			log.name, log.log_type, log.time
		),
	)
	baru = _hitung_ulang(shift, log.employee, log.shift_start)
	if baru:
		frappe.get_doc("Attendance", baru).add_comment(
			"Comment",
			_("Dihitung ulang dari check-in offline {0}, menggantikan {1} ({2}).").format(log.name, lama.name, lama.status),
		)
	else:
		_kabari_hrd(
			log,
			_(
				"Attendance {0} ({1}) dibatalkan karena check-in offline {2} baru terkirim, "
				"tetapi Attendance baru gagal dibuat. Mohon dicek."
			).format(lama.name, lama.status, frappe.bold(log.employee_name)),
		)


def _attendance_otomatis(row) -> bool:
	return (
		row.owner == "Administrator"
		and not row.attendance_request
		and not row.leave_application
		and row.status in STATUS_ATTENDANCE_OTOMATIS
	)


def _hitung_ulang(shift, employee: str, shift_start) -> str | None:
	"""Hitung Attendance satu karyawan untuk satu shift, sama seperti Shift Type._process."""
	from hrms.hr.doctype.employee_checkin.employee_checkin import mark_attendance_and_link_log

	filters = {
		"employee": employee,
		"shift": shift.name,
		"shift_start": shift_start,
		"attendance": ("is", "not set"),
		"offshift": 0,
	}
	# log yang sempat ditandai skip karena Attendance lama sudah ada
	for name in frappe.get_all("Employee Checkin", filters={**filters, "skip_auto_attendance": 1}, pluck="name"):
		frappe.db.set_value("Employee Checkin", name, "skip_auto_attendance", 0, update_modified=False)

	logs = frappe.get_all(
		"Employee Checkin",
		fields=[
			"name",
			"employee",
			"log_type",
			"time",
			"shift",
			"shift_start",
			"shift_end",
			"shift_actual_start",
			"shift_actual_end",
			"device_id",
		],
		filters={**filters, "skip_auto_attendance": 0},
		order_by="time",
	)
	if not logs:
		return None
	tanggal = getdate(shift_start)
	if not shift.should_mark_attendance(employee, tanggal):
		return None

	status, working_hours, late_entry, early_exit, in_time, out_time = shift.get_attendance(logs)
	attendance = mark_attendance_and_link_log(
		logs, status, tanggal, working_hours, late_entry, early_exit, in_time, out_time, shift.name
	)
	return attendance.name if attendance else None


def _kabari_hrd(log, pesan: str):
	from hrms.xsha.lembur import _hrd_users

	for user in _hrd_users():
		notification = frappe.new_doc("PWA Notification")
		notification.from_user = "Administrator"
		notification.to_user = user
		notification.message = pesan
		notification.reference_document_type = "Employee Checkin"
		notification.reference_document_name = log.name
		notification.insert(ignore_permissions=True)


# ---------------------------------------------------------------------------
# Service worker dengan scope /hrms
# ---------------------------------------------------------------------------


@frappe.whitelist(allow_guest=True, methods=["GET"])
def service_worker(**kwargs):
	"""Sajikan sw.js hasil build dengan header Service-Worker-Allowed.

	File aslinya ada di /assets/hrms/frontend/sw.js (disajikan nginx), sehingga scope-nya
	hanya /assets/hrms/frontend/ dan tidak bisa menangani halaman /hrms saat server down.
	Lewat endpoint ini service worker boleh didaftarkan dengan scope /hrms.
	Parameter ?config= (konfigurasi Firebase) dibaca oleh sw.js sendiri dari URL.
	"""
	from werkzeug.wrappers import Response

	path = frappe.get_app_path("hrms", "public", "frontend", "sw.js")
	with open(path, "rb") as f:
		isi = f.read()
	response = Response(isi, mimetype="application/javascript")
	response.headers["Service-Worker-Allowed"] = "/hrms"
	response.headers["Cache-Control"] = "no-cache"
	return response
