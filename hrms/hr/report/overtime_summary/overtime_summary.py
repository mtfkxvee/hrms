# Copyright (c) 2026, X-Sha
"""Rekap Data Lembur (detail) dan Rekap Lembur Berbayar per karyawan untuk Keuangan."""

import frappe
from frappe import _
from frappe.utils import cint, getdate


def execute(filters=None):
	filters = frappe._dict(filters or {})
	if filters.view == "Summary per Employee":
		return _kolom_rekap(), _data_rekap(filters)
	return _kolom_detail(), _data_detail(filters)


def _conditions(filters):
	cond = {"tanggal": ["between", [getdate(filters.from_date), getdate(filters.to_date)]]}
	for f in ("employee", "branch", "kompensasi", "status"):
		if filters.get(f):
			cond[f] = filters.get(f)
	return cond


def _kolom_detail():
	return [
		{"label": _("Overtime Request"), "fieldname": "name", "fieldtype": "Link", "options": "Overtime Request", "width": 140},
		{"label": _("Employee"), "fieldname": "employee", "fieldtype": "Link", "options": "Employee", "width": 120},
		{"label": _("Employee Name"), "fieldname": "employee_name", "fieldtype": "Data", "width": 170},
		{"label": _("Branch"), "fieldname": "branch", "fieldtype": "Link", "options": "Branch", "width": 100},
		{"label": _("Date"), "fieldname": "tanggal", "fieldtype": "Date", "width": 100},
		{"label": _("Planned"), "fieldname": "rencana", "fieldtype": "Data", "width": 110},
		{"label": _("Started"), "fieldname": "mulai_lembur", "fieldtype": "Datetime", "width": 150},
		{"label": _("Ended"), "fieldname": "selesai_lembur", "fieldtype": "Datetime", "width": 150},
		{"label": _("Actual Minutes"), "fieldname": "menit_realisasi", "fieldtype": "Int", "width": 90},
		{"label": _("Counted Hours"), "fieldname": "jam_dihitung", "fieldtype": "Int", "width": 90},
		{"label": _("Public Holiday"), "fieldname": "tanggal_merah", "fieldtype": "Check", "width": 80},
		{"label": _("Compensation"), "fieldname": "kompensasi", "fieldtype": "Data", "width": 120},
		{"label": _("Status"), "fieldname": "status", "fieldtype": "Data", "width": 140},
		{"label": _("PJK Status"), "fieldname": "status_pjk", "fieldtype": "Data", "width": 100},
		{"label": _("SPL Number"), "fieldname": "nomor_spl", "fieldtype": "Data", "width": 130},
		{"label": _("Work"), "fieldname": "pekerjaan", "fieldtype": "Data", "width": 200},
	]


def _data_detail(filters):
	rows = frappe.get_all(
		"Overtime Request",
		filters=_conditions(filters),
		fields=[
			"name", "employee", "employee_name", "branch", "tanggal", "jam_mulai", "jam_selesai",
			"mulai_lembur", "selesai_lembur", "menit_realisasi", "jam_dihitung", "tanggal_merah",
			"kompensasi", "status", "status_pjk", "nomor_spl", "pekerjaan",
		],
		order_by="tanggal asc, employee_name asc",
	)
	for r in rows:
		r.rencana = f"{str(r.jam_mulai)[:5]} - {str(r.jam_selesai)[:5]}"
	return rows


def _kolom_rekap():
	return [
		{"label": _("Employee"), "fieldname": "employee", "fieldtype": "Link", "options": "Employee", "width": 120},
		{"label": _("Employee Name"), "fieldname": "employee_name", "fieldtype": "Data", "width": 180},
		{"label": _("Branch"), "fieldname": "branch", "fieldtype": "Link", "options": "Branch", "width": 110},
		{"label": _("Overtime Count"), "fieldname": "jumlah", "fieldtype": "Int", "width": 110},
		{"label": _("Working Day Hours"), "fieldname": "jam_hari_kerja", "fieldtype": "Int", "width": 120},
		{"label": _("Public Holiday Hours"), "fieldname": "jam_tanggal_merah", "fieldtype": "Int", "width": 130},
		{"label": _("Total Hours"), "fieldname": "total_jam", "fieldtype": "Int", "width": 100},
		{"label": _("Equivalent Hours (holiday x2)"), "fieldname": "jam_setara", "fieldtype": "Int", "width": 150},
	]


def _data_rekap(filters):
	cond = _conditions(filters)
	cond["status"] = "Completed"
	rekap = {}
	for r in frappe.get_all(
		"Overtime Request",
		filters=cond,
		fields=["employee", "employee_name", "branch", "jam_dihitung", "tanggal_merah"],
	):
		x = rekap.setdefault(
			r.employee,
			frappe._dict(employee=r.employee, employee_name=r.employee_name, branch=r.branch, jumlah=0,
			             jam_hari_kerja=0, jam_tanggal_merah=0),
		)
		x.jumlah += 1
		if cint(r.tanggal_merah):
			x.jam_tanggal_merah += cint(r.jam_dihitung)
		else:
			x.jam_hari_kerja += cint(r.jam_dihitung)
	hasil = sorted(rekap.values(), key=lambda x: (x.branch or "", x.employee_name or ""))
	for x in hasil:
		x.total_jam = x.jam_hari_kerja + x.jam_tanggal_merah
		x.jam_setara = x.jam_hari_kerja + 2 * x.jam_tanggal_merah
	return hasil
