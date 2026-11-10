"""I10: ringkasan harian pengajuan yang belum diproses, dikirim ke masing-masing approver."""

from collections import defaultdict

import frappe
from frappe import _
from frappe.utils import format_date, get_url_to_form

PENDING_SOURCES = (
	# doctype, field approver, filter "belum diproses", label
	("Leave Application", "leave_approver", {"status": "Open", "docstatus": 0}, "Izin / Sakit / Cuti"),
	("Shift Request", "approver", {"status": "Draft", "docstatus": 0}, "Ganti Shift"),
)


def get_pending_by_approver() -> dict[str, list[dict]]:
	pending = defaultdict(list)
	for doctype, approver_field, filters, label in PENDING_SOURCES:
		rows = frappe.get_all(
			doctype,
			filters={**filters, approver_field: ["is", "set"]},
			fields=["name", "employee_name", "from_date", "to_date", approver_field + " as approver"],
			order_by="from_date asc",
		)
		for row in rows:
			row.update(doctype=doctype, label=label)
			pending[row.approver].append(row)
	return pending


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
