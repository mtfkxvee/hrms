"""Auto checkout X-PEOPLE.

Karyawan yang sudah check-in tapi sampai jendela "Allow check-out after shift end time"
habis (di X-Sha 120 menit) belum check-out dicatatkan check-out otomatis (permintaan Lutpi,
25 Nov 2026). Tanpa ini log IN tanpa
pasangan dihitung 0 jam kerja dan Attendance-nya jadi Absent.

Aturan:
- jam check-out yang dicatat = jam pulang jadwal (shift_end), bukan jam job berjalan,
  supaya log tetap masuk shift yang sama dan tidak dihitung pulang cepat / lembur
- log ditandai device_id = DEVICE_ID supaya HRD bisa memfilter
- lokasi disalin dari log IN (validasi radius bawaan butuh latitude/longitude); selfie
  (custom_foto_selfie, wajib) dilewati karena tidak ada foto
- check-out asli yang masuk belakangan lewat mode offline menggantikan log otomatis ini
  (hrms.xsha.offline._perbaiki memanggil hapus_auto_checkout)

Pemicunya sama dengan saat auto attendance memproses shift itu (jam pulang + jendela), jadi
keduanya bisa jalan berbarengan. Kalau Attendance otomatis (Absent) sudah terlanjur dibuat,
log OUT tetap dibuat lalu Attendance dibatalkan dan dihitung ulang lewat
hrms.xsha.offline.perbaiki_attendance. Attendance buatan HR / dari pengajuan tidak disentuh.
"""

import datetime

import frappe
from frappe.utils import get_datetime, now_datetime

# cadangan kalau Shift Type tidak punya jendela check-out
BATAS_DEFAULT = datetime.timedelta(hours=2)
# kandidat dicari mundur sejauh ini; log IN yang lebih tua dibiarkan (sudah diproses HR)
JANGKAUAN = datetime.timedelta(days=2)
DEVICE_ID = "AUTO CHECKOUT"
# berlaku untuk shift yang jam pulangnya setelah fitur ini live (keputusan Lutpi 25 Nov 2026:
# Absent sebelum itu tidak diubah mundur)
MULAI = datetime.datetime(2026, 11, 25, 13, 59)


def jalankan():
	"""Scheduler (cron tiap 15 menit)."""
	sekarang = now_datetime()
	shift_aktif = frappe.get_all("Shift Type", filters={"enable_auto_attendance": 1}, pluck="name")
	if not shift_aktif:
		return

	kandidat = frappe.get_all(
		"Employee Checkin",
		filters={
			"log_type": "IN",
			"offshift": 0,
			"skip_auto_attendance": 0,
			"shift": ("in", shift_aktif),
			"shift_end": ("between", [max(sekarang - JANGKAUAN, MULAI), sekarang]),
		},
		fields=["employee", "shift", "shift_start"],
		distinct=True,
	)

	for row in kandidat:
		try:
			nama = checkout_otomatis(row.employee, row.shift, row.shift_start)
			frappe.db.commit()
			if nama:
				frappe.enqueue(
					"hrms.xsha.offline.perbaiki_attendance",
					checkin=nama,
					queue="short",
					enqueue_after_commit=True,
				)
		except Exception:
			frappe.db.rollback()
			frappe.log_error(title=f"X-PEOPLE auto checkout {row.employee} {row.shift_start}")


def checkout_otomatis(employee: str, shift: str, shift_start) -> str | None:
	"""Buat log OUT otomatis untuk satu karyawan di satu shift. Nama log, atau None."""
	logs = frappe.get_all(
		"Employee Checkin",
		filters={"employee": employee, "shift": shift, "shift_start": shift_start, "offshift": 0},
		fields=["name", "log_type", "time", "shift_end", "shift_actual_end", "latitude", "longitude", "attendance"],
		order_by="time desc",
	)
	if not logs:
		return None
	terakhir = logs[0]
	if terakhir.log_type != "IN":
		return None  # sudah check-out
	if terakhir.attendance and not _attendance_otomatis(terakhir.attendance):
		return None  # sudah ditangani HR

	shift_end = get_datetime(terakhir.shift_end)
	if now_datetime() < shift_end + batas(shift):
		return None

	waktu = shift_end
	jam_in = get_datetime(terakhir.time)
	if waktu <= jam_in:
		# check-in setelah jam pulang jadwal (masih dalam jendela shift): pasangkan 1 menit setelahnya
		waktu = jam_in + datetime.timedelta(minutes=1)

	latitude, longitude = terakhir.latitude, terakhir.longitude
	if not (latitude or longitude):
		latitude, longitude = _lokasi_cabang(employee)

	doc = frappe.get_doc(
		{
			"doctype": "Employee Checkin",
			"employee": employee,
			"log_type": "OUT",
			"time": waktu,
			"device_id": DEVICE_ID,
			"latitude": latitude,
			"longitude": longitude,
		}
	)
	doc.flags.ignore_permissions = True
	doc.flags.ignore_mandatory = True  # selfie wajib untuk check-out dari aplikasi, bukan log otomatis
	doc.insert()

	if doc.offshift or doc.shift != shift or get_datetime(doc.shift_start) != get_datetime(shift_start):
		# jam pulang jadwal ternyata jatuh ke shift lain: jangan dipaksakan
		frappe.throw(f"Auto checkout {employee}: log jatuh ke shift {doc.shift} {doc.shift_start}, dibatalkan.")

	doc.add_comment(
		"Comment",
		f"Check-out otomatis: belum check-out {int(batas(shift).total_seconds() // 60)} menit setelah jam "
		f"pulang jadwal. Jam dicatat = jam pulang jadwal (IN: {terakhir.name}).",
	)
	return doc.name


def hapus_auto_checkout(employee: str, shift: str, shift_start, kecuali: str | None = None) -> list[str]:
	"""Hapus log OUT otomatis di satu shift (dipakai saat check-out asli masuk belakangan)."""
	filters = {
		"employee": employee,
		"shift": shift,
		"shift_start": shift_start,
		"device_id": DEVICE_ID,
		"log_type": "OUT",
		"attendance": ("is", "not set"),
	}
	if kecuali:
		filters["name"] = ("!=", kecuali)
	names = frappe.get_all("Employee Checkin", filters=filters, pluck="name")
	for name in names:
		frappe.delete_doc("Employee Checkin", name, ignore_permissions=True, force=True)
	return names


def batas(shift: str) -> datetime.timedelta:
	"""Jeda setelah jam pulang sebelum check-out otomatis = jendela check-out Shift Type."""
	menit = frappe.get_cached_value("Shift Type", shift, "allow_check_out_after_shift_end_time")
	return datetime.timedelta(minutes=int(menit)) if menit else BATAS_DEFAULT


def _attendance_otomatis(attendance: str) -> bool:
	from hrms.xsha.offline import _attendance_otomatis as otomatis

	row = frappe.db.get_value(
		"Attendance",
		attendance,
		["owner", "status", "attendance_request", "leave_application", "docstatus"],
		as_dict=True,
	)
	return bool(row and row.docstatus == 1 and otomatis(row))


def _lokasi_cabang(employee: str):
	from hrms.xsha.rules import get_branch_shift_location

	lokasi = get_branch_shift_location(employee)
	if lokasi:
		return lokasi.latitude, lokasi.longitude
	return None, None
