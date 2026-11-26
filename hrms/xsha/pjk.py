"""Pengambilan PJK saat check-in terlambat / check-out lebih awal (X-Sha).

Aturan (disepakati 25 Nov 2026):
- Telat/pulang cepat dihitung dari jam masuk/pulang shift. Masih dalam toleransi shift = tidak ditawari.
- Jam PJK = dibulatkan seperti lembur (jam penuh + 1 bila sisa >= 45 menit), minimal 1 jam.
- Ditawari (pop-up) hanya bila saldo PJK cukup; saldo kurang = langsung tercatat telat/pulang cepat.
- Setelah PJK N jam, jam masuk mundur / jam pulang maju N jam; lewat toleransi dari situ tetap tercatat.
- Saldo dipotong saat check-in/out disimpan (Employee Checkin.pjk_jam) dan dikembalikan bila
  check-in itu dihapus/diubah jamnya, atau ternyata bukan check-in pertama / check-out terakhir.
- Mode offline tidak menawarkan PJK.
"""

import datetime

import frappe
from frappe import bold
from frappe.utils import cint, flt, formatdate, get_datetime

from hrms.hr.doctype.pjk_balance.pjk_balance import get_saldo, ubah_saldo_pjk

CHECKIN = "Employee Checkin"
FIELD = "pjk_jam"


def _ada_field() -> bool:
	return frappe.get_meta(CHECKIN).has_field(FIELD)


def label_menit(menit: int) -> str:
	jam, sisa = divmod(max(0, cint(menit)), 60)
	if jam and sisa:
		return f"{jam} jam {sisa} menit"
	return f"{jam} jam" if jam else f"{sisa} menit"


# ---------------------------------------------------------------------------
# Hitungan
# ---------------------------------------------------------------------------


def hitung_pjk(employee: str, log_type: str, waktu) -> dict | None:
	"""Tawaran PJK untuk check-in (IN) terlambat / check-out (OUT) lebih awal pada waktu itu.

	None bila tidak ada yang perlu ditawarkan (tidak telat, di luar shift, saldo kurang, dst).
	"""
	from hrms.hr.doctype.shift_assignment.shift_assignment import get_actual_start_end_datetime_of_shift
	from hrms.xsha.lembur import bulatkan_jam

	if log_type not in ("IN", "OUT") or not _ada_field():
		return None
	waktu = get_datetime(waktu)
	shift = get_actual_start_end_datetime_of_shift(employee, waktu, True)
	if not shift or not shift.get("shift_type"):
		return None
	st = shift.shift_type
	mulai, selesai = get_datetime(shift.start_datetime), get_datetime(shift.end_datetime)

	if log_type == "IN":
		if not cint(st.enable_late_entry_marking):
			return None
		# hanya check-in pertama di shift ini yang dipakai untuk Attendance
		if frappe.db.exists(CHECKIN, {"employee": employee, "log_type": "IN", "shift": st.name, "shift_start": mulai}):
			return None
		menit = int((waktu - mulai).total_seconds() // 60)
		toleransi = cint(st.late_entry_grace_period)
	else:
		if not cint(st.enable_early_exit_marking):
			return None
		# tanpa check-in di shift ini tidak ada Attendance yang bisa ditutup PJK
		if not frappe.db.exists(CHECKIN, {"employee": employee, "log_type": "IN", "shift": st.name, "shift_start": mulai}):
			return None
		menit = int((selesai - waktu).total_seconds() // 60)
		toleransi = cint(st.early_exit_grace_period)

	if menit <= toleransi:
		return None

	jam = max(1, bulatkan_jam(menit))
	saldo = get_saldo(employee)
	if saldo < jam:
		return None

	sisa = menit - jam * 60
	return {
		"log_type": log_type,
		"menit": menit,
		"label_menit": label_menit(menit),
		"jam": jam,
		"saldo": saldo,
		# setelah PJK masih lewat toleransi: tetap tercatat telat / pulang cepat
		"tetap_menit": sisa if sisa > toleransi else 0,
		"label_tetap": label_menit(sisa) if sisa > toleransi else "",
		"shift": st.name,
		"shift_start": mulai,
	}


@frappe.whitelist()
def cek_pjk(log_type: str) -> dict:
	"""Dipanggil aplikasi sebelum check-in/out: perlu tampilkan pop-up PJK atau tidak."""
	from frappe.utils import now_datetime

	from hrms.xsha.checkin import _current_employee

	hasil = hitung_pjk(_current_employee(), log_type, now_datetime())
	if not hasil:
		return {}
	hasil.pop("shift_start", None)
	return hasil


# ---------------------------------------------------------------------------
# Dipakai saat check-in disimpan (hrms.xsha.checkin.buat_checkin)
# ---------------------------------------------------------------------------


def siapkan(checkin, ambil_pjk) -> dict | None:
	"""Sebelum insert: hitung ulang di server dan tandai check-in memakai PJK.

	ambil_pjk = jumlah jam yang disetujui karyawan di pop-up. Kalau hitungan ulang berbeda
	(mis. pop-up dibiarkan terbuka sampai lewat pembulatan berikutnya), PJK tidak dipakai
	supaya saldo tidak terpotong lebih dari yang disetujui.
	"""
	disetujui = cint(ambil_pjk)
	if disetujui <= 0:
		return None
	hasil = hitung_pjk(checkin.employee, checkin.log_type, checkin.time)
	if not hasil or hasil["jam"] != disetujui:
		return None  # sudah tidak memenuhi / jam berubah: check-in biasa
	checkin.set(FIELD, hasil["jam"])
	checkin.flags.xsha_pjk = True
	return hasil


def potong_saldo(checkin, hasil: dict):
	"""Sesudah insert: potong saldo PJK dan kabari atasan."""
	jenis = "Datang terlambat" if checkin.log_type == "IN" else "Pulang lebih awal"
	tanggal = formatdate(hasil["shift_start"])
	try:
		frappe.db.savepoint("xsha_pjk_potong")
		ubah_saldo_pjk(
			checkin.employee,
			-flt(hasil["jam"]),
			"Pengambilan PJK",
			checkin.name,
			f"{jenis} {hasil['label_menit']}, {tanggal}",
		)
	except Exception:
		# mis. saldo berubah di detik yang sama: check-in tetap tersimpan, tanpa PJK
		frappe.db.rollback(save_point="xsha_pjk_potong")
		frappe.clear_messages()
		checkin.db_set(FIELD, 0, update_modified=False)
		frappe.log_error(title=f"PJK potong saldo {checkin.employee}")
		return
	try:
		frappe.db.savepoint("xsha_pjk_notif")
		_kabari_atasan(checkin, hasil, jenis, tanggal)
	except Exception:
		# notifikasi gagal tidak boleh menggagalkan check-in
		frappe.db.rollback(save_point="xsha_pjk_notif")
		frappe.log_error(title=f"PJK notifikasi atasan {checkin.employee}")


def _kabari_atasan(checkin, hasil: dict, jenis: str, tanggal: str):
	from hrms.xsha.lembur import get_atasan

	atasan = get_atasan(checkin.employee)
	if not atasan or atasan == frappe.session.user:
		return
	nama = frappe.db.get_value("Employee", checkin.employee, "employee_name") or checkin.employee
	notif = frappe.new_doc("PWA Notification")
	notif.from_user = frappe.session.user
	notif.to_user = atasan
	notif.message = (
		f"{bold(nama)} memakai PJK {hasil['jam']} jam ({jenis.lower()} {hasil['label_menit']}) pada {tanggal}"
	)
	notif.insert(ignore_permissions=True)


def kembalikan(checkin_name: str, employee: str, jam, alasan: str):
	"""Batalkan pemakaian PJK sebuah check-in: saldo kembali, tercatat di riwayat."""
	jam = flt(jam)
	if jam <= 0:
		return
	ubah_saldo_pjk(employee, jam, "Pembatalan PJK", checkin_name, alasan)


# ---------------------------------------------------------------------------
# Kait ke Employee Checkin (hooks)
# ---------------------------------------------------------------------------


def checkin_validate(doc, method=None):
	if not _ada_field():
		return
	if doc.is_new():
		# hanya buat_checkin (pop-up PJK) yang boleh mengisi pjk_jam
		if not doc.flags.get("xsha_pjk"):
			doc.set(FIELD, 0)
		return
	before = doc.get_doc_before_save()
	if not before:
		return
	lama = flt(before.get(FIELD))
	if flt(doc.get(FIELD)) != lama and not doc.flags.get("xsha_pjk"):
		doc.set(FIELD, lama)  # tidak bisa diubah manual; koreksi saldo lewat PJK Balance
	if lama and get_datetime(doc.time) != get_datetime(before.time):
		kembalikan(doc.name, doc.employee, lama, f"Jam {doc.log_type} diubah, PJK dibatalkan")
		doc.set(FIELD, 0)


def checkin_on_trash(doc, method=None):
	if _ada_field() and flt(doc.get(FIELD)):
		kembalikan(doc.name, doc.employee, doc.get(FIELD), f"{doc.log_type} dihapus, PJK dibatalkan")


# ---------------------------------------------------------------------------
# Kait ke Attendance (dipanggil dari hrms.xsha.lembur.attendance_before_submit / on_submit)
# ---------------------------------------------------------------------------


def attendance_before_submit(doc, shift_start, shift_end, grace_masuk, grace_pulang):
	"""Hapus tanda telat / pulang cepat yang sudah ditutup PJK; tandai PJK yang tidak terpakai."""
	if not _ada_field():
		return
	logs = frappe.get_all(
		CHECKIN,
		filters={"employee": doc.employee, "shift": doc.shift, "shift_start": shift_start, FIELD: [">", 0]},
		fields=["name", "log_type", "time", FIELD],
	)
	if not logs:
		return

	in_time = get_datetime(doc.in_time) if doc.in_time else None
	out_time = get_datetime(doc.out_time) if doc.out_time else None
	batal, jam_dipakai = [], 0

	for log in logs:
		t = get_datetime(log.time)
		jam = flt(log.get(FIELD))
		if log.log_type == "IN" and in_time and t == in_time:
			batas = shift_start + datetime.timedelta(hours=jam, minutes=cint(grace_masuk))
			doc.late_entry = 1 if in_time > batas else 0
			jam_dipakai += jam
		elif log.log_type == "OUT" and out_time and t == out_time:
			batas = shift_end - datetime.timedelta(hours=jam, minutes=cint(grace_pulang))
			doc.early_exit = 1 if out_time < batas else 0
			jam_dipakai += jam
		else:
			batal.append(log)

	_status_dengan_pjk(doc, jam_dipakai)
	if batal:
		doc.flags.xsha_pjk_batal = batal


def _status_dengan_pjk(doc, jam_pjk: float):
	"""Jam PJK dihitung sebagai jam kerja supaya pulang cepat ber-PJK tidak jadi Half Day/Absent."""
	if not jam_pjk or doc.status not in ("Half Day", "Absent") or not flt(doc.working_hours):
		return
	half, absent = frappe.db.get_value(
		"Shift Type", doc.shift, ["working_hours_threshold_for_half_day", "working_hours_threshold_for_absent"]
	)
	total = flt(doc.working_hours) + jam_pjk
	if flt(absent) and total < flt(absent):
		return
	if flt(half) and total < flt(half):
		doc.status = "Half Day"
		return
	doc.status = "Present"


def attendance_on_submit(doc):
	for log in doc.flags.get("xsha_pjk_batal") or []:
		alasan = "Bukan check-in pertama" if log.log_type == "IN" else "Bukan check-out terakhir"
		kembalikan(log.name, doc.employee, log.get(FIELD), f"{alasan} di shift ini, PJK dibatalkan")
		frappe.db.set_value(CHECKIN, log.name, FIELD, 0, update_modified=False)


def menit_pjk_awal(employee: str, tanggal, shift_type: str) -> int:
	"""Menit tambahan toleransi telat dari PJK check-in pada tanggal itu (HR Dashboard)."""
	if not _ada_field():
		return 0
	from hrms.xsha.lembur import _rentang_shift

	shift = _rentang_shift(shift_type, tanggal) if shift_type else None
	if not shift:
		return 0
	jam = frappe.db.get_value(
		CHECKIN,
		{"employee": employee, "log_type": "IN", "shift": shift_type, "shift_start": shift[0], FIELD: [">", 0]},
		FIELD,
	)
	return int(flt(jam) * 60)
