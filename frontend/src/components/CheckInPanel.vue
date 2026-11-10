<template>
	<div class="flex flex-col bg-white rounded w-full py-6 px-4 border-none">
		<h2 class="text-lg font-bold text-gray-900">
			{{ __("Hey, {0} 👋", [employee?.data?.first_name]) }}
		</h2>

		<template v-if="settings.data?.allow_employee_checkin_from_mobile_app">
			<div class="font-medium text-sm text-gray-500 mt-1.5" v-if="lastLog">
				<span>{{ __("Last {0} was at {1}", [__(lastLogType), formatTimestamp(lastLog.time)]) }}</span>
				<span class="whitespace-pre"> &middot; </span>
				<router-link :to="{ name: 'EmployeeCheckinListView' }" v-slot="{ navigate }">
					<span @click="navigate" class="underline">View List</span>
				</router-link>
			</div>
			<Button
				class="mt-4 mb-1 drop-shadow-sm py-5 text-base"
				id="open-checkin-modal"
				@click="handleEmployeeCheckin"
			>
				<template #prefix>
					<FeatherIcon
						:name="nextAction.action === 'IN' ? 'arrow-right-circle' : 'arrow-left-circle'"
						class="w-4"
					/>
				</template>
				{{ nextAction.label }}
			</Button>
		</template>

		<div v-else class="font-medium text-sm text-gray-500 mt-1.5">
			{{ dayjs().format("ddd, D MMMM, YYYY") }}
		</div>
	</div>

	<ion-modal
		v-if="settings.data?.allow_employee_checkin_from_mobile_app"
		ref="modal"
		trigger="open-checkin-modal"
		:initial-breakpoint="1"
		:breakpoints="[0, 1]"
		@didDismiss="stopCamera"
	>
		<div class="h-120 w-full flex flex-col items-center justify-center gap-5 p-4 mb-5">
			<div class="flex flex-col gap-1.5 mt-2 items-center justify-center">
				<div class="font-bold text-xl">
					{{ dayjs(checkinTimestamp).format("hh:mm:ss a") }}
				</div>
				<div class="font-medium text-gray-500 text-sm">
					{{ dayjs().format("D MMM, YYYY") }}
				</div>
			</div>

			<template v-if="geolocationRequired">
				<div class="flex flex-col items-center gap-1 text-center">
					<span v-if="locationStatus" class="font-medium text-gray-500 text-sm">
						{{ locationStatus }}
					</span>
					<span v-if="locationHelp" class="text-xs text-gray-500">{{ locationHelp }}</span>
					<button
						v-if="locationState === 'error'"
						@click="fetchLocation"
						class="mt-1 px-4 py-1.5 rounded-lg bg-gray-100 text-gray-700 text-sm font-medium"
					>
						🔄 {{ __("Coba Lagi") }}
					</button>
				</div>
				<div
					v-if="locationState === 'ready'"
					class="rounded border-4 translate-z-0 block overflow-hidden w-full h-170"
				>
					<iframe
						width="100%"
						height="170"
						frameborder="0"
						scrolling="no"
						marginheight="0"
						marginwidth="0"
						style="border: 0"
						:src="`https://maps.google.com/maps?q=${latitude},${longitude}&hl=en&z=15&amp;output=embed`"
					>
					</iframe>
				</div>
			</template>

			<!-- SELFIE -->
			<div class="w-full flex flex-col items-center gap-2">
				<img
					v-if="photoPreview"
					:src="photoPreview"
					class="w-full max-w-xs rounded-lg border"
					style="max-height: 200px; object-fit: cover"
				/>
				<video
					v-show="cameraActive && !photoPreview"
					ref="videoRef"
					autoplay
					playsinline
					class="w-full max-w-xs rounded-lg border"
					style="max-height: 200px; object-fit: cover"
				></video>
				<canvas ref="canvasRef" style="display: none"></canvas>

				<div class="flex gap-2 w-full">
					<button
						v-if="!cameraActive && !photoPreview"
						@click="openCamera"
						class="w-full py-2 rounded-lg bg-gray-100 text-gray-700 text-sm font-medium"
					>
						📷 {{ __("Buka Kamera") }}
					</button>
					<button
						v-if="cameraActive && !photoPreview"
						@click="capturePhoto"
						class="w-full py-2 rounded-lg bg-blue-500 text-white text-sm font-medium"
					>
						📸 {{ __("Ambil Foto") }}
					</button>
					<button
						v-if="photoPreview"
						@click="retakePhoto"
						class="w-full py-2 rounded-lg bg-gray-100 text-gray-700 text-sm font-medium"
					>
						🔄 {{ __("Foto Ulang") }}
					</button>
				</div>

				<span v-if="photoStatus" class="text-xs text-gray-500 text-center">{{ photoStatus }}</span>
			</div>

			<Button
				:loading="createCheckin.loading"
				:disabled="!canConfirm"
				variant="solid"
				class="w-full py-5 text-sm disabled:bg-gray-700"
				@click="submitLog(nextAction.action)"
			>
				{{ __("Confirm {0}", [nextAction.label]) }}
			</Button>
			<span v-if="confirmHint" class="text-xs text-gray-500 -mt-3">{{ confirmHint }}</span>
		</div>
	</ion-modal>
</template>

<script setup>
import { createResource, createListResource, toast, FeatherIcon } from "frappe-ui"
import { computed, inject, ref, onMounted, onBeforeUnmount } from "vue"
import { IonModal, modalController } from "@ionic/vue"
import { formatTimestamp } from "@/utils/formatters"

const DOCTYPE = "Employee Checkin"
// A08: rata-rata kecerahan minimal (0-255). Server memakai batas yang sama.
const MIN_BRIGHTNESS = 35
const MAX_PHOTO_SIDE = 960

const socket = inject("$socket")
const employee = inject("$employee")
const dayjs = inject("$dayjs")
const __ = inject("$translate")
const checkinTimestamp = ref(null)
const latitude = ref(0)
const longitude = ref(0)
const locationStatus = ref("")
const locationHelp = ref("")
const locationState = ref("idle") // idle | locating | ready | error

const videoRef = ref(null)
const canvasRef = ref(null)
const cameraActive = ref(false)
const photoPreview = ref(null)
const photoData = ref(null)
const photoStatus = ref("")
let cameraStream = null

const settings = createResource({
	url: "hrms.api.get_hr_settings",
	auto: true,
})

const geolocationRequired = computed(() => Boolean(settings.data?.allow_geolocation_tracking))

const checkins = createListResource({
	doctype: DOCTYPE,
	fields: ["name", "employee", "employee_name", "log_type", "time", "device_id", "shift_actual_end"],
	filters: { employee: employee.data.name },
	orderBy: "time desc",
})
checkins.reload()

const lastLog = computed(() => {
	if (checkins.list.loading || !checkins.data) return {}
	return checkins.data[0]
})

const lastLogType = computed(() => {
	return lastLog?.value?.log_type === "IN" ? "check-in" : "check-out"
})

// A15: check-in yang tidak ditutup (lupa check-out) tidak boleh membuat tombol esok hari
// tetap "Check Out". Log IN dianggap sudah lewat jika jendela shift-nya sudah selesai,
// atau (untuk log tanpa shift) jika bukan dari hari ini.
function isOpenCheckin(log) {
	if (log?.log_type !== "IN") return false
	if (log.shift_actual_end) return dayjs().isBefore(dayjs(log.shift_actual_end))
	return dayjs(log.time).isSame(dayjs(), "day")
}

const nextAction = computed(() => {
	return isOpenCheckin(lastLog.value)
		? { action: "OUT", label: __("Check Out") }
		: { action: "IN", label: __("Check In") }
})

const canConfirm = computed(() => {
	if (!photoData.value) return false
	if (geolocationRequired.value && locationState.value !== "ready") return false
	return true
})

const confirmHint = computed(() => {
	if (!photoData.value) return __("Ambil selfie terlebih dahulu")
	if (geolocationRequired.value && locationState.value !== "ready") return __("Menunggu lokasi terbaca")
	return ""
})

// A18: lokasi dengan akurasi tinggi, timeout, tombol Coba Lagi, dan panduan izin.
function handleLocationSuccess(position) {
	latitude.value = position.coords.latitude
	longitude.value = position.coords.longitude
	locationState.value = "ready"
	locationHelp.value = ""
	locationStatus.value = [
		__("Latitude: {0}°", [Number(latitude.value).toFixed(5)]),
		__("Longitude: {0}°", [Number(longitude.value).toFixed(5)]),
		__("Akurasi ±{0} m", [Math.round(position.coords.accuracy || 0)]),
	].join(", ")
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

const fetchLocation = () => {
	if (!navigator.geolocation) {
		locationState.value = "error"
		locationStatus.value = __("Geolocation is not supported by your current browser")
		locationHelp.value = ""
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

const handleEmployeeCheckin = () => {
	checkinTimestamp.value = dayjs().format("YYYY-MM-DD HH:mm:ss")
	photoPreview.value = null
	photoData.value = null
	photoStatus.value = ""
	cameraActive.value = false
	locationState.value = "idle"
	if (geolocationRequired.value) fetchLocation()
}

function stopCamera() {
	if (cameraStream) cameraStream.getTracks().forEach((t) => t.stop())
	cameraStream = null
	cameraActive.value = false
}

const openCamera = async () => {
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
	// sampling tiap 16 piksel cukup untuk rata-rata
	for (let i = 0; i < data.length; i += 64) {
		total += 0.299 * data[i] + 0.587 * data[i + 1] + 0.114 * data[i + 2]
		count++
	}
	return count ? total / count : 0
}

// A07/A09: foto tidak di-upload saat diambil. Foto disimpan di memori dan dikirim
// bersama check-in saat Confirm, lalu server menyimpannya sebagai file private.
const capturePhoto = () => {
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

	// A08: tolak foto gelap / kamera tertutup
	if (averageBrightness(ctx, canvas.width, canvas.height) < MIN_BRIGHTNESS) {
		photoData.value = null
		photoStatus.value = __("Foto terlalu gelap. Pastikan wajah terlihat jelas, lalu foto ulang.")
		return
	}
	photoData.value = dataUrl
	photoStatus.value = __("Foto siap")
}

const retakePhoto = () => {
	photoPreview.value = null
	photoData.value = null
	photoStatus.value = ""
	openCamera()
}

const createCheckin = createResource({
	url: "hrms.xsha.checkin.create_checkin",
})

const submitLog = (logType) => {
	const actionLabel = logType === "IN" ? __("Check-in") : __("Check-out")
	createCheckin.submit(
		{
			log_type: logType,
			latitude: latitude.value,
			longitude: longitude.value,
			photo: photoData.value,
		},
		{
			onSuccess(data) {
				stopCamera()
				modalController.dismiss()
				checkins.reload()
				// A10: log di luar shift tidak akan menjadi Attendance, beri tahu karyawan
				if (data?.offshift) {
					toast({
						title: __("Tercatat di luar shift"),
						text: __(
							"{0} tersimpan, tetapi tidak ada shift yang cocok dengan jam ini sehingga tidak dihitung sebagai kehadiran. Hubungi HR jika ini keliru.",
							[actionLabel]
						),
						icon: "alert-triangle",
						position: "bottom-center",
						iconClasses: "text-yellow-500",
						timeout: 8,
					})
					return
				}
				toast({
					title: __("Success"),
					text: __("{0} successful!", [actionLabel]),
					icon: "check-circle",
					position: "bottom-center",
					iconClasses: "text-green-500",
				})
			},
			onError(error) {
				const messages = error.messages?.length ? error.messages : [error.message]
				for (const message of messages) {
					toast({
						title: __("Error"),
						text: __("{0} failed!", [actionLabel]) + (message ? `: ${message}` : ""),
						icon: "alert-circle",
						position: "bottom-center",
						iconClasses: "text-red-500",
					})
				}
			},
		}
	)
}

onMounted(() => {
	socket.emit("doctype_subscribe", DOCTYPE)
	socket.on("list_update", (data) => {
		if (data.doctype == DOCTYPE) checkins.reload()
	})
})

onBeforeUnmount(() => {
	stopCamera()
	socket.emit("doctype_unsubscribe", DOCTYPE)
	socket.off("list_update")
})
</script>
