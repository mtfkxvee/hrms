// X-Sha: antrean offline check-in/out dan Mulai/Selesai Lembur.
//
// Alur: kirim langsung ke endpoint biasa. Jika server tidak bisa dihubungi (jaringan putus,
// 5xx, timeout), data disimpan di HP dengan jam server terkoreksi (jam.js), lalu dikirim
// otomatis ke hrms.xsha.offline.* saat app dibuka/aktif lagi dan server sudah hidup.
// Data yang ditolak server (mis. di luar radius) tetap tampil dengan alasannya sampai dihapus.
import { reactive } from "vue"

import { semuaItem, simpanItem, hapusItem } from "./idb"
import { jamServerMs } from "./jam"

const ENDPOINT_SYNC = {
	checkin: "hrms.xsha.offline.sync_checkin",
	lembur: "hrms.xsha.offline.sync_lembur",
}
const BATAS_KIRIM_LANGSUNG_MS = 12000
const BATAS_SYNC_MS = 30000
const INTERVAL_COBA_MS = 30000

export const antrean = reactive({
	items: [], // { id, user, jenis, params, waktu_ms, dibuat, status: menunggu|ditolak, pesan }
	mengirim: false,
	kondisi: "", // "" | putus | perlu_login
	termuat: false,
})

const pendengar = new Set()
// dipanggil setiap ada item antrean yang berhasil terkirim: (item, data)
export function saatTerkirim(fn) {
	pendengar.add(fn)
	return () => pendengar.delete(fn)
}

function userAktif() {
	const cookies = new URLSearchParams(document.cookie.split("; ").join("&"))
	const user = cookies.get("user_id")
	return user && user !== "Guest" ? user : null
}

function idBaru() {
	if (window.crypto?.randomUUID) return window.crypto.randomUUID()
	return `${Date.now()}-${Math.random().toString(16).slice(2)}-${Math.random().toString(16).slice(2)}`
}

export const itemMenunggu = () => antrean.items.filter((i) => i.status === "menunggu")

let userTermuat = null

export async function muatAntrean() {
	try {
		const user = userAktif()
		userTermuat = user
		const rows = await semuaItem()
		antrean.items = (rows || []).filter((r) => r.user === user).sort((a, b) => a.dibuat - b.dibuat)
	} catch (e) {
		console.error("Gagal membaca antrean offline", e)
	}
	antrean.termuat = true
}

async function tambah(jenis, params, waktu_ms) {
	const item = {
		id: idBaru(),
		user: userAktif(),
		jenis,
		params,
		waktu_ms,
		dibuat: Date.now(),
		status: "menunggu",
		pesan: "",
	}
	await simpanItem(item)
	antrean.items.push(item)
	return item
}

export async function buangItem(id) {
	await hapusItem(id)
	antrean.items = antrean.items.filter((i) => i.id !== id)
}

// ---------------------------------------------------------------------------
// Request
// ---------------------------------------------------------------------------

function bersihkanHtml(teks) {
	const div = document.createElement("div")
	div.innerHTML = teks
	return (div.textContent || div.innerText || "").trim()
}

function pesanDariRespons(data) {
	const pesan = []
	try {
		for (const m of JSON.parse(data._server_messages || "[]")) {
			try {
				pesan.push(JSON.parse(m).message)
			} catch (e) {
				pesan.push(m)
			}
		}
	} catch (e) {
		// abaikan format yang tidak dikenal
	}
	if (!pesan.length && data._error_message) pesan.push(data._error_message)
	if (!pesan.length && data.exception) pesan.push(String(data.exception).split(":").slice(1).join(":") || data.exception)
	return pesan.filter(Boolean).map(bersihkanHtml).join(" ")
}

async function denganBatas(promise, ms) {
	let timer
	const batas = new Promise((_, reject) => {
		timer = setTimeout(() => reject(new Error("timeout")), ms)
	})
	try {
		return await Promise.race([promise, batas])
	} finally {
		clearTimeout(timer)
	}
}

// Hasil: { jenis: ok|putus|csrf|perlu_login|ditolak, data?, pesan? }
async function panggil(method, params, batasMs) {
	const ctrl = new AbortController()
	let response
	try {
		response = await denganBatas(
			fetch(`/api/method/${method}`, {
				method: "POST",
				credentials: "same-origin",
				headers: {
					Accept: "application/json",
					"Content-Type": "application/json; charset=utf-8",
					"X-Frappe-Site-Name": window.location.hostname,
					"X-Frappe-CSRF-Token": window.csrf_token || "",
				},
				body: JSON.stringify(params),
				signal: ctrl.signal,
			}),
			batasMs
		)
	} catch (e) {
		ctrl.abort()
		return { jenis: "putus", pesan: e.message }
	}

	let data = null
	try {
		data = await response.json()
	} catch (e) {
		// halaman error nginx/Cloudflare (bukan JSON)
	}
	if (response.ok && data) return { jenis: "ok", data: data.message }
	if (!data || response.status >= 500) {
		return { jenis: "putus", pesan: data ? pesanDariRespons(data) : `HTTP ${response.status}` }
	}
	if (data.exc_type === "CSRFTokenError") return { jenis: "csrf" }
	if (response.status === 401 || data.exc_type === "AuthenticationError") return { jenis: "perlu_login" }
	if (response.status === 403 && !(await masihLogin())) return { jenis: "perlu_login" }
	return { jenis: "ditolak", pesan: pesanDariRespons(data) || `HTTP ${response.status}` }
}

async function masihLogin() {
	try {
		const res = await denganBatas(fetch("/api/method/frappe.auth.get_logged_user", { credentials: "same-origin" }), 10000)
		return res.ok
	} catch (e) {
		return true // tidak bisa dipastikan: anggap masih login, jangan buang sesi
	}
}

// true = server bisa dihubungi dan token terbaru sudah dipasang
async function segarkanCsrf() {
	try {
		const res = await denganBatas(
			fetch("/api/method/hrms.api.get_csrf.get_csrf_token", { credentials: "same-origin" }),
			10000
		)
		if (res.status === 401 || res.status === 403) {
			antrean.kondisi = "perlu_login"
			return false
		}
		if (!res.ok) {
			antrean.kondisi = "putus"
			return false
		}
		const data = await res.json()
		if (data.message) window.csrf_token = data.message
		return true
	} catch (e) {
		antrean.kondisi = "putus"
		return false
	}
}

async function panggilDenganCsrf(method, params, batasMs) {
	let hasil = await panggil(method, params, batasMs)
	if (hasil.jenis === "csrf" && (await segarkanCsrf())) hasil = await panggil(method, params, batasMs)
	if (hasil.jenis === "csrf") hasil = { jenis: "ditolak", pesan: "Sesi tidak valid. Muat ulang aplikasi." }
	return hasil
}

// ---------------------------------------------------------------------------
// Dipakai panel check-in / lembur
// ---------------------------------------------------------------------------

/**
 * Kirim langsung; jika server tidak bisa dihubungi, simpan ke antrean.
 * @param {string} jenis "checkin" | "lembur"
 * @param {string} methodLangsung endpoint biasa (jam server)
 * @param {object} params parameter endpoint biasa
 * @param {object} ekstraSync parameter tambahan khusus endpoint sync (mis. { aksi })
 * @returns {Promise<{ok?: boolean, data?: any, tersimpan?: boolean, waktu_ms?: number, pesan?: string, perluLogin?: boolean}>}
 */
export async function kirimAtauSimpan(jenis, methodLangsung, params, ekstraSync = {}) {
	const waktu_ms = jamServerMs() // jam saat karyawan menekan Confirm
	const simpan = async () => {
		await tambah(jenis, { ...params, ...ekstraSync }, waktu_ms)
		jadwalkanCoba()
		return { tersimpan: true, waktu_ms }
	}

	// masih ada antrean: ikut antre supaya urutan (IN sebelum OUT, mulai sebelum selesai) terjaga
	if (itemMenunggu().length) {
		const hasil = await simpan()
		kirimSemua()
		return hasil
	}

	const hasil = await panggilDenganCsrf(methodLangsung, params, BATAS_KIRIM_LANGSUNG_MS)
	if (hasil.jenis === "ok") {
		antrean.kondisi = ""
		return { ok: true, data: hasil.data }
	}
	if (hasil.jenis === "putus") {
		antrean.kondisi = "putus"
		return simpan()
	}
	if (hasil.jenis === "perlu_login") return { perluLogin: true, pesan: "Sesi login habis. Silakan login ulang." }
	return { pesan: hasil.pesan }
}

// ---------------------------------------------------------------------------
// Sinkronisasi
// ---------------------------------------------------------------------------

let prosesKirim = null

export function kirimSemua() {
	if (!prosesKirim) prosesKirim = _kirimSemua().finally(() => (prosesKirim = null))
	return prosesKirim
}

async function _kirimSemua() {
	if (!antrean.termuat) await muatAntrean()
	const daftar = itemMenunggu()
	if (!daftar.length) return

	antrean.mengirim = true
	try {
		if (!(await segarkanCsrf())) return
		for (const item of daftar) {
			const hasil = await panggilDenganCsrf(
				ENDPOINT_SYNC[item.jenis],
				{ ...item.params, offline_id: item.id, waktu_ms: item.waktu_ms },
				BATAS_SYNC_MS
			)
			if (hasil.jenis === "ok") {
				await hapusItem(item.id)
				antrean.items = antrean.items.filter((i) => i.id !== item.id)
				for (const fn of pendengar) {
					try {
						fn(item, hasil.data)
					} catch (e) {
						console.error(e)
					}
				}
				continue
			}
			if (hasil.jenis === "putus") {
				antrean.kondisi = "putus"
				return
			}
			if (hasil.jenis === "perlu_login") {
				antrean.kondisi = "perlu_login"
				return
			}
			// ditolak server: simpan alasannya, lanjut ke item berikutnya
			item.status = "ditolak"
			item.pesan = hasil.pesan
			await simpanItem(item)
		}
		antrean.kondisi = ""
	} finally {
		antrean.mengirim = false
	}
}

let timerCoba = null

function jadwalkanCoba() {
	if (timerCoba) return
	timerCoba = setInterval(() => {
		if (!itemMenunggu().length) {
			clearInterval(timerCoba)
			timerCoba = null
			return
		}
		if (document.visibilityState === "visible") kirimSemua()
	}, INTERVAL_COBA_MS)
}

let sudahMulai = false

// dipanggil router setiap navigasi saat login; murah jika user tidak berubah
export function mulaiSinkronOtomatis() {
	if (sudahMulai && userTermuat === userAktif()) return
	const pertamaKali = !sudahMulai
	sudahMulai = true
	if (antrean.kondisi === "perlu_login") antrean.kondisi = ""
	muatAntrean().then(() => {
		if (itemMenunggu().length) {
			jadwalkanCoba()
			kirimSemua()
		}
	})
	if (!pertamaKali) return
	window.addEventListener("online", () => kirimSemua())
	document.addEventListener("visibilitychange", () => {
		if (document.visibilityState === "visible") kirimSemua()
	})
}
