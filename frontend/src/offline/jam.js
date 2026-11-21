// X-Sha: jam server untuk data offline.
// Setiap respons API membawa header Date (jam server). Selisihnya dengan jam HP disimpan,
// sehingga saat server down jam check-in = jam HP + selisih terakhir (jam HP yang salah
// setel tetap terkoreksi). Dikirim ke server sebagai epoch ms UTC.
const KEY = "xp:selisih_jam"
const MAKS_LATENSI_MS = 5000

let selisih = baca()

function baca() {
	try {
		const data = JSON.parse(localStorage.getItem(KEY) || "null")
		return typeof data?.selisih === "number" ? data.selisih : 0
	} catch (e) {
		return 0
	}
}

function catat(input, response, mulai) {
	const url = typeof input === "string" ? input : input?.url || ""
	if (!url.includes("/api/method/")) return
	if (url.startsWith("http") && !url.startsWith(location.origin)) return
	const header = response.headers.get("date")
	const server = header ? Date.parse(header) : NaN
	if (Number.isNaN(server)) return
	const selesai = Date.now()
	if (selesai - mulai > MAKS_LATENSI_MS) return // latensi tinggi: kurang akurat
	// header Date dibulatkan ke bawah per detik, jadi +500 ms sebagai rata-rata
	selisih = server + 500 - (mulai + selesai) / 2
	try {
		localStorage.setItem(KEY, JSON.stringify({ selisih, pada: selesai }))
	} catch (e) {
		// penyimpanan penuh/diblokir: tetap pakai nilai di memori
	}
}

export function pasangPencatatJam() {
	if (window.__xpPencatatJam) return
	window.__xpPencatatJam = true
	const fetchAsli = window.fetch.bind(window)
	window.fetch = async (input, init) => {
		const mulai = Date.now()
		const response = await fetchAsli(input, init)
		try {
			catat(input, response, mulai)
		} catch (e) {
			// pencatat jam tidak boleh mengganggu request
		}
		return response
	}
}

export const jamServerMs = () => Math.round(Date.now() + selisih)

// dipasang saat modul dimuat; main.js mengimpor modul ini paling awal supaya request
// pertama (resource auto) juga tercatat
pasangPencatatJam()
