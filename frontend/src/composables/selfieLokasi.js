// X-Sha: selfie + lokasi untuk Mulai/Selesai Lembur.
// Aturannya sama dengan CheckInPanel (A07/A08/A18): foto disimpan di memori, foto gelap
// ditolak, lokasi akurasi tinggi dengan tombol Coba Lagi. Selfie lewat kamera bawaan HP.
import { ref, computed, inject } from "vue"
import { bukaKameraHP, prosesFotoKamera } from "@/composables/kameraHP"

export function useSelfieLokasi() {
	const __ = inject("$translate")

	const latitude = ref(0)
	const longitude = ref(0)
	const locationState = ref("idle") // idle | locating | ready | error
	const locationStatus = ref("")
	const locationHelp = ref("")

	const inputFotoRef = ref(null)
	const memprosesFoto = ref(false)
	const photoPreview = ref(null)
	const photoData = ref(null)
	const photoStatus = ref("")

	function handleLocationSuccess(position) {
		latitude.value = position.coords.latitude
		longitude.value = position.coords.longitude
		locationState.value = "ready"
		locationHelp.value = ""
		locationStatus.value = [__("Latitude: {0}°", [Number(latitude.value).toFixed(5)]), __("Longitude: {0}°", [Number(longitude.value).toFixed(5)]), __("Akurasi ±{0} m", [Math.round(position.coords.accuracy || 0)])].join(", ")
	}

	function handleLocationError(error) {
		locationState.value = "error"
		const messages = {
			1: [
				__("Izin lokasi ditolak."),
				__("Buka pengaturan browser/HP, izinkan Lokasi untuk situs ini, lalu tekan Coba Lagi."),
			],
			2: [__("Lokasi tidak tersedia."), __("Pastikan GPS menyala dan coba di area terbuka.")],
			3: [__("Lokasi terlalu lama dibaca."), __("Pastikan GPS menyala, lalu tekan Coba Lagi.")],
		}
		const [status, help] = messages[error?.code] || [__("Lokasi gagal dibaca."), ""]
		locationStatus.value = status
		locationHelp.value = help
	}

	function fetchLocation() {
		if (!navigator.geolocation) {
			locationState.value = "error"
			locationStatus.value = __("Geolocation is not supported by your current browser")
			return
		}
		locationState.value = "locating"
		locationStatus.value = __("Locating...")
		locationHelp.value = ""
		navigator.geolocation.getCurrentPosition(handleLocationSuccess, handleLocationError, {
			enableHighAccuracy: true,
			timeout: 20000,
			maximumAge: 0,
		})
	}

	function ambilFoto() {
		photoStatus.value = ""
		bukaKameraHP(inputFotoRef.value)
	}

	async function onFotoDipilih(event) {
		const file = event.target.files?.[0]
		if (!file) return
		memprosesFoto.value = true
		try {
			const hasil = await prosesFotoKamera(file, __)
			photoPreview.value = hasil.preview || null
			photoData.value = hasil.ok ? hasil.dataUrl : null
			photoStatus.value = hasil.pesan || ""
		} finally {
			memprosesFoto.value = false
			event.target.value = ""
		}
	}

	function reset() {
		photoPreview.value = null
		photoData.value = null
		photoStatus.value = ""
		locationState.value = "idle"
		locationStatus.value = ""
		locationHelp.value = ""
	}

	const siap = computed(() => Boolean(photoData.value) && locationState.value === "ready")
	const petunjuk = computed(() => {
		if (!photoData.value) return __("Ambil selfie terlebih dahulu")
		if (locationState.value !== "ready") return __("Menunggu lokasi terbaca")
		return ""
	})

	return {
		latitude,
		longitude,
		locationState,
		locationStatus,
		locationHelp,
		inputFotoRef,
		memprosesFoto,
		photoPreview,
		photoData,
		photoStatus,
		fetchLocation,
		ambilFoto,
		onFotoDipilih,
		reset,
		siap,
		petunjuk,
	}
}
