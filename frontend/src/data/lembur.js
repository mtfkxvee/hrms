// X-Sha: data Pengajuan Lembur untuk aplikasi HRMS (server: hrms/xsha/lembur.py)
import { createResource } from "frappe-ui"

import dayjs from "@/utils/dayjs"

export const LEMBUR_DOCTYPE = "Overtime Request"
const API = "hrms.xsha.lembur."

export const STATUS_WARNA = {
	"Pending Supervisor": "orange",
	"Pending HR": "orange",
	Approved: "blue",
	"In Progress": "blue",
	"Pending Confirmation": "orange",
	Completed: "green",
	Rejected: "red",
	Cancelled: "gray",
}

export const jamPendek = (value) => (value ? String(value).split(":").slice(0, 2).join(".") : "")

export const labelTanggal = (row) => dayjs(row.tanggal).format("ddd, D MMM")

export const labelJam = (row) => `${jamPendek(row.jam_mulai)} - ${jamPendek(row.jam_selesai)}`

const transform = (data) =>
	(data || []).map((row) => {
		row.doctype = LEMBUR_DOCTYPE
		return row
	})

export const myLembur = createResource({
	url: API + "get_lembur_list",
	params: { limit: 10 },
	auto: true,
	cache: "hrms:my_lembur",
	transform,
})

export const teamLembur = createResource({
	url: API + "get_lembur_list",
	params: { for_approval: 1, limit: 10 },
	auto: true,
	cache: "hrms:team_lembur",
	transform,
})

export const lemburHariIni = createResource({
	url: API + "get_lembur_hari_ini",
	auto: true,
})

export const saldoPjk = createResource({
	url: API + "get_saldo_pjk_saya",
	auto: true,
	cache: "hrms:saldo_pjk",
})

export const reloadLembur = () => {
	myLembur.reload()
	teamLembur.reload()
	lemburHariIni.reload()
	saldoPjk.reload()
}
