"""Endpoint check-in X-Sha untuk aplikasi PWA.

Menggantikan alur lama (upload selfie publik saat foto diambil, lalu insert log terpisah):
- A07: selfie disimpan sebagai file private dan di-attach ke log check-in
- A08: foto yang terlalu gelap ditolak di server
- A09: foto dan log dibuat dalam satu request; jika check-in gagal, file ikut dibatalkan
- A10: respons memberi tahu jika log berada di luar shift (tidak akan dihitung)
- A17: jam memakai jam server (lihat rules.checkin_before_validate)
"""

import base64
import io

import frappe
from frappe import _
from frappe.utils import cint, flt, now_datetime

SELFIE_FIELD = "custom_foto_selfie"
MAX_PHOTO_BYTES = 3 * 1024 * 1024
# Rata-rata kecerahan (0-255) minimal. Foto kamera tertutup biasanya < 15.
MIN_BRIGHTNESS = 35


def _current_employee() -> str:
	employee = frappe.db.get_value(
		"Employee", {"user_id": frappe.session.user, "status": "Active"}, "name"
	)
	if not employee:
		frappe.throw(_("Akun Anda belum terhubung ke data karyawan aktif. Hubungi HR."))
	return employee


def decode_photo(photo: str) -> bytes:
	"""Terima data URL / base64 JPEG atau PNG, kembalikan bytes."""
	if "," in photo and photo.startswith("data:"):
		photo = photo.split(",", 1)[1]
	try:
		content = base64.b64decode(photo, validate=True)
	except Exception:
		frappe.throw(_("Format foto tidak valid."))

	if len(content) > MAX_PHOTO_BYTES:
		frappe.throw(_("Ukuran foto terlalu besar (maksimal 3 MB)."))
	if not (content[:3] == b"\xff\xd8\xff" or content[:8] == b"\x89PNG\r\n\x1a\n"):
		frappe.throw(_("Foto harus berformat JPEG atau PNG."))
	return content


def photo_brightness(content: bytes) -> float:
	from PIL import Image, ImageStat

	with Image.open(io.BytesIO(content)) as img:
		img = img.convert("L")
		img.thumbnail((200, 200))
		return ImageStat.Stat(img).mean[0]


def validate_photo(content: bytes):
	if photo_brightness(content) < MIN_BRIGHTNESS:
		frappe.throw(
			_("Foto terlalu gelap. Pastikan wajah terlihat jelas dan kamera tidak tertutup, lalu foto ulang."),
			title=_("Foto Tidak Jelas"),
		)


def selfie_required() -> bool:
	field = frappe.get_meta("Employee Checkin").get_field(SELFIE_FIELD)
	return bool(field and field.reqd)


@frappe.whitelist(methods=["POST"])
def create_checkin(log_type: str, latitude=None, longitude=None, photo: str | None = None) -> dict:
	if log_type not in ("IN", "OUT"):
		frappe.throw(_("Jenis log tidak valid."))

	employee = _current_employee()
	has_selfie_field = frappe.get_meta("Employee Checkin").has_field(SELFIE_FIELD)

	content = None
	if photo:
		content = decode_photo(photo)
		validate_photo(content)
	elif has_selfie_field and selfie_required():
		frappe.throw(_("Selfie wajib diambil sebelum check-in."))

	file_doc = None
	try:
		if content and has_selfie_field:
			stamp = now_datetime().strftime("%Y%m%d-%H%M%S")
			file_doc = frappe.get_doc(
				{
					"doctype": "File",
					"file_name": f"selfie_{employee}_{stamp}_{frappe.generate_hash(length=6)}.jpg",
					"is_private": 1,
					"content": content,
				}
			)
			file_doc.flags.ignore_permissions = True
			file_doc.insert()

		checkin = frappe.get_doc(
			{
				"doctype": "Employee Checkin",
				"employee": employee,
				"log_type": log_type,
				"time": now_datetime(),
				"latitude": flt(latitude) if latitude not in (None, "") else None,
				"longitude": flt(longitude) if longitude not in (None, "") else None,
			}
		)
		if file_doc:
			checkin.set(SELFIE_FIELD, file_doc.file_url)
		checkin.insert()

		if file_doc:
			file_doc.db_set(
				{
					"attached_to_doctype": "Employee Checkin",
					"attached_to_name": checkin.name,
					"attached_to_field": SELFIE_FIELD,
				}
			)
	except Exception:
		# File fisik baru juga dihapus oleh File.on_rollback saat request di-rollback,
		# tapi hapus eksplisit supaya tidak bergantung pada urutan rollback.
		if file_doc and file_doc.name:
			try:
				file_doc.delete(ignore_permissions=True)
			except Exception:
				pass
		raise

	return {
		"name": checkin.name,
		"log_type": checkin.log_type,
		"time": checkin.time,
		"shift": checkin.shift,
		"offshift": cint(checkin.offshift),
	}
