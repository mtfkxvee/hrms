// X-Sha: selfie absen & lembur memakai aplikasi kamera bawaan HP (input file + capture),
// bukan kamera di dalam Chrome (getUserMedia) yang sering hitam di HP lama (mis. Vivo Android 8.1).
// Aturan foto tetap sama: diperkecil, foto gelap ditolak (server memakai batas yang sama),
// dan foto lama (mis. dipilih dari galeri) ditolak.

export const MIN_BRIGHTNESS = 35 // rata-rata kecerahan minimal (0-255)
const MAX_PHOTO_SIDE = 960
const MAX_UMUR_FOTO_MS = 2 * 60 * 1000

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
		return { ok: false, pesan: __("File yang dipilih bukan foto.") }
	}
	if (file.lastModified && Date.now() - file.lastModified > MAX_UMUR_FOTO_MS) {
		return {
			ok: false,
			pesan: __("Gunakan foto yang baru diambil dari kamera, bukan foto lama dari galeri."),
		}
	}

	if (!file.size) {
		// kamera mengembalikan file kosong (biasanya Chrome sempat ditutup sistem karena memori HP penuh)
		return {
			ok: false,
			pesan: __("Foto tidak tersimpan. Tutup aplikasi lain yang terbuka, lalu foto ulang."),
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
						"Format foto HEIF tidak didukung. Matikan 'Gambar efisiensi tinggi (HEIF)' di pengaturan Kamera, lalu foto ulang."
				  )
				: __(
						"Foto tidak bisa dibaca. Coba matikan 'Gambar efisiensi tinggi (HEIF)' di pengaturan Kamera, lalu foto ulang."
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
	const dataUrl = canvas.toDataURL("image/jpeg", 0.8)

	if (kecerahanRata(ctx, canvas.width, canvas.height) < MIN_BRIGHTNESS) {
		return {
			ok: false,
			preview: dataUrl,
			pesan: __("Foto terlalu gelap. Pastikan wajah terlihat jelas, lalu foto ulang."),
		}
	}
	return { ok: true, dataUrl, preview: dataUrl, pesan: __("Foto siap") }
}
