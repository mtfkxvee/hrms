<template>
	<div class="flex flex-col bg-white rounded w-full py-6 px-4 border-none">
		<h2 class="text-lg font-bold text-gray-900">
			{{ __("Hey, {0} 👋", [employee?.data?.first_name]) }}
		</h2>

		<template v-if="settings.data?.allow_employee_checkin_from_mobile_app">
			<div class="font-medium text-sm text-gray-500 mt-1.5" v-if="lastLog">
				<span>{{ __("Last {0} was at {1}", [__(lastLogType), formatTimestamp(lastLog.time)]) }}</span>
				<span v-if="lastLog.offline" class="text-orange-600"> ({{ __("belum terkirim") }})</span>
				<span v-if="lastLogOtomatis"> ({{ __("otomatis, lupa check-out") }})</span>
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
				<!-- X-Sha: selfie lewat aplikasi kamera bawaan HP -->
				<input
					ref="inputFotoRef"
					type="file"
					accept="image/*"
					capture="user"
					style="display: none"
					@change="onFotoDipilih"
				/>

				<div class="flex gap-2 w-full">
					<button
						v-if="!photoPreview"
						@click="ambilFoto"
						:disabled="memprosesFoto"
						class="w-full py-2 rounded-lg bg-blue-500 text-white text-sm font-medium disabled:opacity-60"
					>
						📷 {{ memprosesFoto ? __("Memproses foto...") : __("Ambil Foto") }}
					</button>
					<button
						v-else
						@click="ambilFoto"
						:disabled="memprosesFoto"
						class="w-full py-2 rounded-lg bg-gray-100 text-gray-700 text-sm font-medium disabled:opacity-60"
					>
						🔄 {{ memprosesFoto ? __("Memproses foto...") : __("Foto Ulang") }}
					</button>
				</div>

				<span v-if="photoStatus" class="text-xs text-gray-500 text-center">{{ photoStatus }}</span>
			</div>

			<Button
				:loading="mengirim"
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
import { antrean, kirimAtauSimpan, saatTerkirim } from "@/offline/antrean"
import { computed, inject, ref, onMounted, onBeforeUnmount } from "vue"
import { IonModal, modalController } from "@ionic/vue"
import { formatTimestamp } from "@/utils/formatters"
import { bukaKameraHP, prosesFotoKamera } from "@/composables/kameraHP"

const DOCTYPE = "Employee Checkin"

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

const inputFotoRef = ref(null)
const memprosesFoto = ref(false)
const photoPreview = ref(null)
const photoData = ref(null)
const photoStatus = ref("")

const settings = createResource({
	url: "hrms.api.get_hr_settings",
	auto: true,
	cache: "hrms:hr_settings", // mode offline: panel check-in tetap tampil saat server down
})

const geolocationRequired = computed(() => Boolean(settings.data?.allow_geolocation_tracking))

const checkins = createListResource({
	doctype: DOCTYPE,
	fields: ["name", "employee", "employee_name", "log_type", "time", "device_id", "shift_actual_end"],
	filters: { employee: employee.data.name },
	orderBy: "time desc",
	cache: ["hrms:checkins", employee.data.name],
})
checkins.reload()

// check-in yang masih di antrean offline (belum sampai server)
const lastOfflineLog = computed(() => {
	const items = antrean.items.filter((i) => i.jenis === "checkin" && i.status === "menunggu")
	const item = items[items.length - 1]
	if (!item) return null
	return {
		log_type: item.params.log_type,
		time: dayjs(item.waktu_ms).format("YYYY-MM-DD HH:mm:ss"),
		offline: true,
	}
})

const lastLog = computed(() => {
	const server = checkins.list.loading && !checkins.data ? null : checkins.data?.[0]
	const offline = lastOfflineLog.value
	if (offline && (!server || dayjs(offline.time).isAfter(dayjs(server.time)))) return offline
	return server || {}
})

const lastLogType = computed(() => {
	return lastLog?.value?.log_type === "IN" ? "check-in" : "check-out"
})

// A15: check-in yang tidak ditutup (lupa check-out) tidak boleh membuat tombol esok hari
// tetap "Check Out". Check-in ber-shift ditutup oleh check-out otomatis server
// (hrms.xsha.auto_checkout) begitu jendela shift habis, jadi selama log terakhir masih IN
// tombol tetap "Check Out". shift_actual_end di log bisa basi (disimpan saat check-in;
// jendela Shift Type bisa diubah sesudahnya), maka dipakai batas aman BATAS_AMAN_JAM
// setelahnya, kalau-kalau check-out otomatis belum/gagal jalan.
// Log tanpa shift: hanya jika dari hari ini.
const BATAS_AMAN_JAM = 3
const AUTO_CHECKOUT = "AUTO CHECKOUT"

function isOpenCheckin(log) {
	if (log?.log_type !== "IN") return false
	if (log.offline) return dayjs(log.time).isAfter(dayjs().subtract(16, "hour"))
	if (log.shift_actual_end) return dayjs().isBefore(dayjs(log.shift_actual_end).add(BATAS_AMAN_JAM, "hour"))
	return dayjs(log.time).isSame(dayjs(), "day")
}

const lastLogOtomatis = computed(() => lastLog.value?.device_id === AUTO_CHECKOUT)

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
	locationState.value = "idle"
	if (geolocationRequired.value) fetchLocation()
}

// X-Sha: selfie lewat kamera bawaan HP (lihat composables/kameraHP.js).
// A07/A09: foto tidak di-upload saat diambil. Foto disimpan di memori dan dikirim
// bersama check-in saat Confirm, lalu server menyimpannya sebagai file private.
// A08: foto gelap / kamera tertutup ditolak.
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

const mengirim = ref(false)

function toastSukses(actionLabel, data) {
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
}

const submitLog = async (logType) => {
	const actionLabel = logType === "IN" ? __("Check-in") : __("Check-out")
	mengirim.value = true
	let hasil
	try {
		hasil = await kirimAtauSimpan("checkin", "hrms.xsha.checkin.create_checkin", {
			log_type: logType,
			latitude: latitude.value,
			longitude: longitude.value,
			photo: photoData.value,
		})
	} catch (error) {
		hasil = { pesan: error?.message }
	} finally {
		mengirim.value = false
	}

	if (hasil.ok || hasil.tersimpan) {
		modalController.dismiss()
	}
	if (hasil.ok) {
		checkins.reload()
		toastSukses(actionLabel, hasil.data)
		return
	}
	if (hasil.tersimpan) {
		// mode offline: tersimpan di HP, dikirim otomatis saat server hidup lagi
		toast({
			title: __("Tersimpan di HP"),
			text: __(
				"Server sedang tidak bisa dihubungi. {0} jam {1} sudah tersimpan dan akan dikirim otomatis saat server kembali normal. Buka aplikasi lagi nanti supaya terkirim.",
				[actionLabel, dayjs(hasil.waktu_ms).format("HH:mm")]
			),
			icon: "clock",
			position: "bottom-center",
			iconClasses: "text-orange-500",
			timeout: 10,
		})
		return
	}
	toast({
		title: __("Error"),
		text: __("{0} failed!", [actionLabel]) + (hasil.pesan ? `: ${hasil.pesan}` : ""),
		icon: "alert-circle",
		position: "bottom-center",
		iconClasses: "text-red-500",
		timeout: 8,
	})
}

const hentikanPendengarAntrean = saatTerkirim((item) => {
	if (item.jenis === "checkin") checkins.reload()
})

onMounted(() => {
	socket.emit("doctype_subscribe", DOCTYPE)
	socket.on("list_update", (data) => {
		if (data.doctype == DOCTYPE) checkins.reload()
	})
})

onBeforeUnmount(() => {
	hentikanPendengarAntrean()
	socket.emit("doctype_unsubscribe", DOCTYPE)
	socket.off("list_update")
})
</script>
