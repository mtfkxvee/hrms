// X-Sha: selfie + lokasi untuk Mulai/Selesai Lembur.
// Aturannya sama dengan CheckInPanel (A07/A08/A18): foto disimpan di memori, foto gelap
// ditolak, lokasi akurasi tinggi dengan tombol Coba Lagi.
import { ref, computed, inject } from "vue"

const MIN_BRIGHTNESS = 35
const MAX_PHOTO_SIDE = 960

export function useSelfieLokasi() {
	const __ = inject("$translate")

	const latitude = ref(0)
	const longitude = ref(0)
	const locationState = ref("idle") // idle | locating | ready | error
	const locationStatus = ref("")
	const locationHelp = ref("")

	const videoRef = ref(null)
	const canvasRef = ref(null)
	const cameraActive = ref(false)
	const photoPreview = ref(null)
	const photoData = ref(null)
	const photoStatus = ref("")
	let cameraStream = null

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

	function stopCamera() {
		if (cameraStream) cameraStream.getTracks().forEach((t) => t.stop())
		cameraStream = null
		cameraActive.value = false
	}

	async function openCamera() {
		try {
			cameraStream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "user" } })
			cameraActive.value = true
			photoStatus.value = ""
			await new Promise((r) => setTimeout(r, 100))
			if (videoRef.value) videoRef.value.srcObject = cameraStream
		} catch (err) {
			photoStatus.value = __("Tidak bisa membuka kamera: {0}", [err.message])
		}
	}

	function averageBrightness(ctx, width, height) {
		const { data } = ctx.getImageData(0, 0, width, height)
		let total = 0
		let count = 0
		for (let i = 0; i < data.length; i += 64) {
			total += 0.299 * data[i] + 0.587 * data[i + 1] + 0.114 * data[i + 2]
			count++
		}
		return count ? total / count : 0
	}

	function capturePhoto() {
		const video = videoRef.value
		const canvas = canvasRef.value
		if (!video || !canvas || !video.videoWidth) return

		const scale = Math.min(1, MAX_PHOTO_SIDE / Math.max(video.videoWidth, video.videoHeight))
		canvas.width = Math.round(video.videoWidth * scale)
		canvas.height = Math.round(video.videoHeight * scale)
		const ctx = canvas.getContext("2d")
		ctx.drawImage(video, 0, 0, canvas.width, canvas.height)
		stopCamera()

		const dataUrl = canvas.toDataURL("image/jpeg", 0.8)
		photoPreview.value = dataUrl
		if (averageBrightness(ctx, canvas.width, canvas.height) < MIN_BRIGHTNESS) {
			photoData.value = null
			photoStatus.value = __("Foto terlalu gelap. Pastikan wajah terlihat jelas, lalu foto ulang.")
			return
		}
		photoData.value = dataUrl
		photoStatus.value = __("Foto siap")
	}

	function retakePhoto() {
		photoPreview.value = null
		photoData.value = null
		photoStatus.value = ""
		openCamera()
	}

	function reset() {
		stopCamera()
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
		videoRef,
		canvasRef,
		cameraActive,
		photoPreview,
		photoData,
		photoStatus,
		fetchLocation,
		openCamera,
		capturePhoto,
		retakePhoto,
		stopCamera,
		reset,
		siap,
		petunjuk,
	}
}
