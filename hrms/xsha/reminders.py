"""I10: ringkasan harian pengajuan yang belum diproses, dikirim ke masing-masing approver."""

from collections import defaultdict

import frappe
from frappe import _
from frappe.utils import format_date, get_url_to_form

LABELS = {
	# doctype -> label di email; tahap HRD diberi akhiran " (HRD)"
	"Leave Application": "Izin / Sakit / Cuti",
	"Shift Request": "Ganti Shift",
	"Attendance Request": "Koreksi Absen",
}


def get_pending_by_approver() -> dict[str, list[dict]]:
	"""Pengajuan 2 lapis (hrms/xsha/approval.py): tahap atasan ke atasan, tahap HRD ke role HRD."""
	from hrms.xsha.approval import HRD, get_all_pending

	pending = defaultdict(list)
	for user, row in get_all_pending():
		label = LABELS[row.doctype] + (" (HRD)" if row.stage == HRD else "")
		pending[user].append(frappe._dict(row, label=label))
	_add_pending_lembur(pending)
	return pending


def _add_pending_lembur(pending):
	"""Lembur: atasan (persetujuan & konfirmasi realisasi) dan HRD (persetujuan tahap 2)."""
	if not frappe.db.exists("DocType", "Overtime Request"):
		return
	from hrms.xsha.approval import final_approver_users

	fields = ["name", "employee", "employee_name", "tanggal as from_date", "tanggal as to_date", "atasan", "status"]
	for row in frappe.get_all(
		"Overtime Request",
		filters={"status": ["in", ["Pending Supervisor", "Pending Confirmation"]], "atasan": ["is", "set"]},
		fields=fields,
		order_by="tanggal asc",
	):
		label = "Lembur" if row.status == "Pending Supervisor" else "Konfirmasi Lembur"
		row.update(doctype="Overtime Request", label=label)
		pending[row.atasan].append(row)

	hrd_rows = frappe.get_all(
		"Overtime Request", filters={"status": "Pending HR"}, fields=fields, order_by="tanggal asc"
	)
	for row in hrd_rows:
		# role HRD selain pemohon; kalau tidak ada, atasan yang memproses tahap HRD
		for user in final_approver_users(row.employee, row.atasan):
			pending[user].append(frappe._dict(row, doctype="Overtime Request", label="Lembur (HRD)"))


def build_message(rows: list[dict]) -> str:
	lines = [
		"<p>" + _("Pengajuan berikut menunggu keputusan Anda:") + "</p>",
		"<table border='1' cellpadding='6' cellspacing='0' style='border-collapse:collapse'>",
		"<tr><th>Jenis</th><th>Karyawan</th><th>Tanggal</th><th>Dokumen</th></tr>",
	]
	for r in rows:
		dates = format_date(r.from_date)
		if r.to_date and r.to_date != r.from_date:
			dates += " - " + format_date(r.to_date)
		link = get_url_to_form(r.doctype, r.name)
		lines.append(
			f"<tr><td>{r.label}</td><td>{frappe.utils.escape_html(r.employee_name or '')}</td>"
			f"<td>{dates}</td><td><a href='{link}'>{r.name}</a></td></tr>"
		)
	lines.append("</table>")
	return "\n".join(lines)


def send_pending_approval_digest():
	"""Dipanggil scheduler harian."""
	for approver, rows in get_pending_by_approver().items():
		if not frappe.db.get_value("User", approver, "enabled"):
			continue
		frappe.sendmail(
			recipients=[approver],
			subject=_("{0} pengajuan menunggu persetujuan").format(len(rows)),
			message=build_message(rows),
		)
