// X-Sha: selfie absen & lembur.
// Default: kamera di dalam aplikasi (getUserMedia). Opsi cadangan: aplikasi kamera bawaan HP
// (input file + capture) untuk HP yang kamera browsernya hitam / tidak bisa dibuka
// (mis. Vivo Android 8.1). Aturan foto sama untuk keduanya: diperkecil, foto gelap ditolak
// (server memakai batas yang sama), dan foto lama dari galeri ditolak.
import { ref } from "vue"

export const MIN_BRIGHTNESS = 35 // rata-rata kecerahan minimal (0-255)
const MAX_PHOTO_SIDE = 960
const MAX_UMUR_FOTO_MS = 2 * 60 * 1000
const SARAN_KAMERA_HP = "Silakan gunakan opsi \"Gunakan aplikasi kamera HP\" di bawah."

/** Buka kamera bawaan HP lewat input file tersembunyi. Harus dipanggil langsung dari klik. */
export function bukaKameraHP(input) {
	if (!input) return
	input.value = "" // supaya memilih foto lagi tetap memicu change
	input.click()
}

function muatGambar(file) {
	return new Promise((resolve, reject) => {
		const url = URL.createObjectURL(file)
		const img = new Image()
		img.onload = () => {
			URL.revokeObjectURL(url)
			resolve(img)
		}
		img.onerror = (err) => {
			URL.revokeObjectURL(url)
			reject(err)
		}
		img.src = url
	})
}

// Coba dua cara: sebagian HP gagal di <img> tapi bisa lewat createImageBitmap, atau sebaliknya.
async function bacaGambar(file) {
	try {
		return await muatGambar(file)
	} catch (err) {
		if (typeof createImageBitmap !== "function") throw err
		return await createImageBitmap(file, { imageOrientation: "from-image" })
	}
}

function kecerahanRata(ctx, width, height) {
	const { data } = ctx.getImageData(0, 0, width, height)
	let total = 0
	let count = 0
	// sampling tiap 16 piksel cukup untuk rata-rata
	for (let i = 0; i < data.length; i += 64) {
		total += 0.299 * data[i] + 0.587 * data[i + 1] + 0.114 * data[i + 2]
		count++
	}
	return count ? total / count : 0
}

/**
 * Olah foto dari kamera HP menjadi data URL JPEG kecil.
 * Hasil: { ok, dataUrl, preview, pesan }. preview tetap diisi untuk foto gelap supaya terlihat.
 */
export async function prosesFotoKamera(file, __) {
	if (!file) return null
	if (file.type && !file.type.startsWith("image/")) {
		return { ok: false, pesan: __("File yang dipilih bukan gambar.") }
	}
	if (file.lastModified && Date.now() - file.lastModified > MAX_UMUR_FOTO_MS) {
		return {
			ok: false,
			pesan: __("Foto harus diambil langsung dari kamera. Foto dari galeri tidak dapat digunakan."),
		}
	}

	if (!file.size) {
		// kamera mengembalikan file kosong (biasanya Chrome sempat ditutup sistem karena memori HP penuh)
		return {
			ok: false,
			pesan: __("Foto gagal tersimpan. Tutup aplikasi lain yang sedang berjalan, lalu ambil ulang foto."),
		}
	}

	let img
	try {
		img = await bacaGambar(file)
	} catch (err) {
		const heif = /hei[cf]/i.test(file.type || "") || /\.hei[cf]$/i.test(file.name || "")
		return {
			ok: false,
			pesan: heif
				? __(
						"Format foto HEIF tidak didukung. Nonaktifkan opsi 'Gambar efisiensi tinggi (HEIF)' pada pengaturan kamera, lalu ambil ulang foto."
				  )
				: __(
						"Foto tidak dapat diproses. Nonaktifkan opsi 'Gambar efisiensi tinggi (HEIF)' pada pengaturan kamera, lalu ambil ulang foto."
				  ),
		}
	}

	const lebar = img.naturalWidth || img.width
	const tinggi = img.naturalHeight || img.height
	const scale = Math.min(1, MAX_PHOTO_SIDE / Math.max(lebar, tinggi))
	const canvas = document.createElement("canvas")
	canvas.width = Math.round(lebar * scale)
	canvas.height = Math.round(tinggi * scale)
	const ctx = canvas.getContext("2d")
	ctx.drawImage(img, 0, 0, canvas.width, canvas.height)
	return hasilCanvas(canvas, ctx, __)
}

function hasilCanvas(canvas, ctx, __, saran = "") {
	const dataUrl = canvas.toDataURL("image/jpeg", 0.8)

	if (kecerahanRata(ctx, canvas.width, canvas.height) < MIN_BRIGHTNESS) {
		return {
			ok: false,
			preview: dataUrl,
			pesan:
				__("Foto terlalu gelap. Pastikan wajah terlihat jelas dan pencahayaan cukup, lalu ambil ulang foto.") +
				(saran ? " " + __(saran) : ""),
		}
	}
	return { ok: true, dataUrl, preview: dataUrl, pesan: __("Foto berhasil diambil.") }
}

/**
 * State + aksi selfie untuk Check-in dan Lembur.
 * Template butuh: <video :ref=videoRef>, <input type=file :ref=inputFotoRef @change=onFotoDipilih>.
 */
export function buatSelfie(__) {
	const videoRef = ref(null)
	const inputFotoRef = ref(null)
	const cameraActive = ref(false)
	const membukaKamera = ref(false)
	const memprosesFoto = ref(false)
	const photoPreview = ref(null)
	const photoData = ref(null)
	const photoStatus = ref("")
	let stream = null
	let sesi = 0 // naik tiap kamera dihentikan; membatalkan pembukaan kamera yang masih berjalan

	function stopCamera() {
		sesi++
		if (stream) stream.getTracks().forEach((t) => t.stop())
		stream = null
		cameraActive.value = false
	}

	async function openCamera() {
		photoStatus.value = ""
		if (!navigator.mediaDevices?.getUserMedia) {
			photoStatus.value = __("Browser ini tidak mendukung akses kamera.") + " " + __(SARAN_KAMERA_HP)
			return
		}
		stopCamera()
		const sesiIni = sesi
		membukaKamera.value = true
		try {
			const s = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "user" } })
			if (sesiIni !== sesi) {
				// pop-up sudah ditutup / kamera dihentikan selama menunggu izin: matikan lagi
				s.getTracks().forEach((t) => t.stop())
				return
			}
			stream = s
			cameraActive.value = true
			await new Promise((r) => setTimeout(r, 100))
			const video = videoRef.value
			if (video && sesiIni === sesi) {
				video.srcObject = s
				// sebagian Android tidak memulai video otomatis walau ada autoplay
				video.play?.()?.catch?.(() => {})
			}
		} catch (err) {
			if (sesiIni !== sesi) return
			stopCamera()
			const ditolak = err?.name === "NotAllowedError" || err?.name === "SecurityError"
			photoStatus.value =
				(ditolak
					? __("Akses kamera ditolak. Aktifkan izin kamera untuk situs ini melalui pengaturan browser.")
					: __("Kamera tidak dapat dibuka.")) +
				" " +
				__(SARAN_KAMERA_HP)
		} finally {
			membukaKamera.value = false
		}
	}

	// A07/A09: foto tidak di-upload saat diambil; disimpan di memori dan dikirim bersama check-in.
	function capturePhoto() {
		const video = videoRef.value
		if (!video || !video.videoWidth) {
			photoStatus.value = __("Tampilan kamera belum tersedia.") + " " + __(SARAN_KAMERA_HP)
			return
		}
		const scale = Math.min(1, MAX_PHOTO_SIDE / Math.max(video.videoWidth, video.videoHeight))
		const canvas = document.createElement("canvas")
		canvas.width = Math.round(video.videoWidth * scale)
		canvas.height = Math.round(video.videoHeight * scale)
		const ctx = canvas.getContext("2d")
		ctx.drawImage(video, 0, 0, canvas.width, canvas.height)
		stopCamera()
		terapkan(hasilCanvas(canvas, ctx, __, SARAN_KAMERA_HP))
	}

	function retakePhoto() {
		photoPreview.value = null
		photoData.value = null
		openCamera()
	}

	// Opsi cadangan: aplikasi kamera bawaan HP
	function pakaiKameraHP() {
		stopCamera()
		photoStatus.value = ""
		bukaKameraHP(inputFotoRef.value)
	}

	async function onFotoDipilih(event) {
		const file = event.target.files?.[0]
		if (!file) return
		memprosesFoto.value = true
		try {
			terapkan(await prosesFotoKamera(file, __))
		} finally {
			memprosesFoto.value = false
			event.target.value = ""
		}
	}

	function terapkan(hasil) {
		if (!hasil) return
		photoPreview.value = hasil.preview || null
		photoData.value = hasil.ok ? hasil.dataUrl : null
		photoStatus.value = hasil.pesan || ""
	}

	function resetFoto() {
		stopCamera()
		photoPreview.value = null
		photoData.value = null
		photoStatus.value = ""
	}

	return {
		videoRef,
		inputFotoRef,
		cameraActive,
		membukaKamera,
		memprosesFoto,
		photoPreview,
		photoData,
		photoStatus,
		openCamera,
		capturePhoto,
		retakePhoto,
		stopCamera,
		pakaiKameraHP,
		onFotoDipilih,
		resetFoto,
	}
}
