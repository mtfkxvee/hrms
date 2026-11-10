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

			<template v-if="settings.data?.allow_geolocation_tracking">
				<span v-if="locationStatus" class="font-medium text-gray-500 text-sm">
					{{ locationStatus }}
				</span>
				<div class="rounded border-4 translate-z-0 block overflow-hidden w-full h-170">
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

			<!-- SELFIE SECTION -->
			<div class="w-full flex flex-col items-center gap-2">
				<img
					v-if="photoPreview"
					:src="photoPreview"
					class="w-full max-w-xs rounded-lg border"
					style="max-height:200px; object-fit:cover;"
				/>
				<video
					v-show="cameraActive && !photoPreview"
					ref="videoRef"
					autoplay
					playsinline
					class="w-full max-w-xs rounded-lg border"
					style="max-height:200px; object-fit:cover;"
				></video>
				<canvas ref="canvasRef" style="display:none;"></canvas>

				<div class="flex gap-2 w-full">
					<button
						v-if="!cameraActive && !photoPreview"
						@click="openCamera"
						class="w-full py-2 rounded-lg bg-gray-100 text-gray-700 text-sm font-medium"
					>
						📷 Buka Kamera
					</button>
					<button
						v-if="cameraActive && !photoPreview"
						@click="capturePhoto"
						class="w-full py-2 rounded-lg bg-blue-500 text-white text-sm font-medium"
					>
						📸 Ambil Foto
					</button>
					<button
						v-if="photoPreview"
						@click="retakePhoto"
						class="w-full py-2 rounded-lg bg-gray-100 text-gray-700 text-sm font-medium"
					>
						🔄 Foto Ulang
					</button>
				</div>

				<span v-if="photoStatus" class="text-xs text-gray-500">{{ photoStatus }}</span>
			</div>
			<!-- END SELFIE SECTION -->

			<Button
				:loading="checkins.insert.loading"
				variant="solid"
				class="w-full py-5 text-sm disabled:bg-gray-700"
				@click="submitLog(nextAction.action)"
			>
				{{ __("Confirm {0}", [nextAction.label]) }}
			</Button>
		</div>
	</ion-modal>
</template>

<script setup>
import { createResource, createListResource, toast, FeatherIcon } from "frappe-ui"
import { computed, inject, ref, onMounted, onBeforeUnmount } from "vue"
import { IonModal, modalController } from "@ionic/vue"
import { formatTimestamp } from "@/utils/formatters"

const DOCTYPE = "Employee Checkin"

const socket = inject("$socket")
const employee = inject("$employee")
const dayjs = inject("$dayjs")
const __ = inject("$translate")
const checkinTimestamp = ref(null)
const latitude = ref(0)
const longitude = ref(0)
const locationStatus = ref("")

const videoRef = ref(null)
const canvasRef = ref(null)
const cameraActive = ref(false)
const photoPreview = ref(null)
const photoUrl = ref(null)
const photoStatus = ref("")
let cameraStream = null
let csrfToken = ""

const settings = createResource({
	url: "hrms.api.get_hr_settings",
	auto: true,
})

const checkins = createListResource({
	doctype: DOCTYPE,
	fields: ["name", "employee", "employee_name", "log_type", "time", "device_id"],
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

const nextAction = computed(() => {
	return lastLog?.value?.log_type === "IN"
		? { action: "OUT", label: __("Check Out") }
		: { action: "IN", label: __("Check In") }
})

function handleLocationSuccess(position) {
	latitude.value = position.coords.latitude
	longitude.value = position.coords.longitude
	locationStatus.value = [
		__("Latitude: {0}°", [Number(latitude.value).toFixed(5)]),
		__("Longitude: {0}°", [Number(longitude.value).toFixed(5)]),
	].join(", ")
}

function handleLocationError(error) {
	locationStatus.value = "Unable to retrieve your location"
	if (error) locationStatus.value += `: ERROR(${error.code}): ${error.message}`
}

const fetchLocation = () => {
	if (!navigator.geolocation) {
		locationStatus.value = __("Geolocation is not supported by your current browser")
	} else {
		locationStatus.value = __("Locating...")
		navigator.geolocation.getCurrentPosition(handleLocationSuccess, handleLocationError)
	}
}

// Ambil CSRF token dari Python API
async function fetchCsrfToken() {
	try {
		const res = await fetch("/api/method/hrms.api.get_csrf.get_csrf_token", {
			credentials: "same-origin",
		})
		const data = await res.json()
		if (data.message) {
			csrfToken = data.message
			console.log("✅ CSRF Token:", csrfToken)
		} else {
			console.warn("❌ CSRF token kosong:", data)
		}
	} catch (e) {
		console.warn("❌ Gagal fetch CSRF token:", e)
	}
}

const handleEmployeeCheckin = async () => {
	checkinTimestamp.value = dayjs().format("YYYY-MM-DD HH:mm:ss")
	photoPreview.value = null
	photoUrl.value = null
	photoStatus.value = ""
	cameraActive.value = false
	await fetchCsrfToken()
	if (settings.data?.allow_geolocation_tracking) fetchLocation()
}

const openCamera = async () => {
	try {
		cameraStream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "user" } })
		cameraActive.value = true
		await new Promise(r => setTimeout(r, 100))
		if (videoRef.value) videoRef.value.srcObject = cameraStream
	} catch (err) {
		photoStatus.value = "❌ Tidak bisa akses kamera: " + err.message
	}
}

const capturePhoto = () => {
	const video = videoRef.value
	const canvas = canvasRef.value
	if (!video || !canvas) return

	canvas.width = video.videoWidth
	canvas.height = video.videoHeight
	canvas.getContext("2d").drawImage(video, 0, 0)

	photoPreview.value = canvas.toDataURL("image/jpeg", 0.8)
	cameraActive.value = false
	if (cameraStream) cameraStream.getTracks().forEach(t => t.stop())

	canvas.toBlob(async (blob) => {
		photoStatus.value = "⏳ Mengupload foto..."
		await fetchCsrfToken()

		try {
			const timestamp = new Date().toISOString().replace(/[:.]/g, "-")
			const filename = `selfie_${employee.data.name}_${timestamp}.jpg`
			const file = new File([blob], filename, { type: "image/jpeg" })

			const formData = new FormData()
			formData.append("file", file)
			formData.append("is_private", 0)

			console.log("Uploading with token:", csrfToken)

			const res = await fetch("/api/method/upload_file", {
				method: "POST",
				headers: {
					"X-Frappe-CSRF-Token": csrfToken,
					"X-Requested-With": "XMLHttpRequest",
				},
				credentials: "same-origin",
				body: formData,
			})

			const data = await res.json()
			console.log("Upload response:", data)

			if (data.message?.file_url) {
				photoUrl.value = data.message.file_url
				photoStatus.value = "✅ Foto siap"
			} else {
				photoStatus.value = "❌ Gagal: " + (data.exc_type || "unknown")
			}
		} catch (err) {
			photoStatus.value = "❌ Error: " + err.message
		}
	}, "image/jpeg", 0.8)
}

const retakePhoto = () => {
	photoPreview.value = null
	photoUrl.value = null
	photoStatus.value = ""
	openCamera()
}

const submitLog = (logType) => {
	const actionLabel = logType === "IN" ? __("Check-in") : __("Check-out")
	checkins.insert.submit(
		{
			employee: employee.data.name,
			log_type: logType,
			time: checkinTimestamp.value,
			latitude: latitude.value,
			longitude: longitude.value,
			custom_foto_selfie: photoUrl.value || "",
		},
		{
			onSuccess() {
				if (cameraStream) cameraStream.getTracks().forEach(t => t.stop())
				modalController.dismiss()
				toast({
					title: __("Success"),
					text: __("{0} successful!", [actionLabel]),
					icon: "check-circle",
					position: "bottom-center",
					iconClasses: "text-green-500",
				})
			},
			onError(error) {
				let messages = error.messages || []
				for (const message of messages) {
					toast({
						title: __("Error"),
						text: message || __("{0} failed!", [actionLabel]),
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
	fetchCsrfToken()
	socket.emit("doctype_subscribe", DOCTYPE)
	socket.on("list_update", (data) => {
		if (data.doctype == DOCTYPE) checkins.reload()
	})
})

onBeforeUnmount(() => {
	if (cameraStream) cameraStream.getTracks().forEach(t => t.stop())
	socket.emit("doctype_unsubscribe", DOCTYPE)
	socket.off("list_update")
})
</script>
