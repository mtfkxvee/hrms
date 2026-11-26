# Copyright (c) 2026, X-Sha
# PJK Balance: saldo PJK per karyawan (satu dokumen per karyawan).
# - HRD mengubah angka Saldo secara manual (wajib isi Keterangan Perubahan) -> tercatat di Riwayat.
# - Sistem menambah/mengurangi lewat ubah_saldo_pjk() (lembur PJK selesai, nanti pengambilan PJK).

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, now_datetime

DOCTYPE = "PJK Balance"


class PJKBalance(Document):
	def validate(self):
		self.saldo = flt(self.saldo, 1)
		if self.saldo < 0:
			frappe.throw(_("Saldo PJK tidak boleh kurang dari 0."))

		sebelum = 0 if self.is_new() else flt(frappe.db.get_value(DOCTYPE, self.name, "saldo"), 1)
		perubahan = flt(self.saldo - sebelum, 1)
		sistem = self.flags.get("pjk_sistem")
		if perubahan and not sistem:
			if not (self.keterangan_perubahan or "").strip():
				frappe.throw(
					_("Isi Keterangan Perubahan dulu (alasan saldo PJK ditambah/dikurangi)."),
					title=_("Keterangan Wajib"),
				)
			self._catat(perubahan, "Manual HRD", None, self.keterangan_perubahan.strip())
		self.keterangan_perubahan = None

	def _catat(self, perubahan, sumber, referensi, keterangan):
		self.append(
			"riwayat",
			{
				"waktu": now_datetime(),
				"sumber": sumber,
				"perubahan": perubahan,
				"saldo_setelah": self.saldo,
				"referensi": referensi,
				"keterangan": keterangan,
				"oleh": frappe.session.user,
			},
		)


def get_saldo(employee: str) -> float:
	if not frappe.db.table_exists(DOCTYPE):
		return 0
	return flt(frappe.db.get_value(DOCTYPE, {"employee": employee}, "saldo"), 1)


def ubah_saldo_pjk(employee: str, jam: float, sumber: str, referensi: str | None = None, keterangan: str | None = None):
	"""Tambah (jam > 0) atau kurangi (jam < 0) saldo PJK karyawan dari sistem, tercatat di Riwayat."""
	jam = flt(jam, 1)
	if not jam:
		return
	name = frappe.db.get_value(DOCTYPE, {"employee": employee}, "name")
	if name:
		frappe.db.get_value(DOCTYPE, name, "name", for_update=True)  # kunci baris: hindari dobel hitung
		doc = frappe.get_doc(DOCTYPE, name)
	else:
		doc = frappe.new_doc(DOCTYPE)
		doc.employee = employee
		doc.saldo = 0
	doc.saldo = flt(flt(doc.saldo) + jam, 1)
	if doc.saldo < 0:
		frappe.throw(_("Saldo PJK tidak cukup."))
	doc.flags.pjk_sistem = True
	doc.flags.ignore_permissions = True
	doc._catat(jam, sumber, referensi, keterangan)
	doc.save()
	return doc.saldo
