<template>
	<!-- Muncul hanya jika hari ini ada SPL (lembur yang sudah disetujui HRD) -->
	<div v-if="spl" class="flex flex-col bg-white rounded w-full py-5 px-4 gap-3">
		<div class="flex flex-row items-center gap-2">
			<LemburIcon class="h-5 w-5 text-gray-700" />
			<h3 class="text-base font-bold text-gray-900">{{ __("Today's Overtime") }}</h3>
		</div>
		<div class="text-sm text-gray-600">
			{{ labelJam(spl) }} &middot; {{ spl.nomor_spl }}
			<div class="mt-1 text-gray-500">{{ spl.pekerjaan }}</div>
			<div v-if="spl.status === 'In Progress'" class="mt-1 text-blue-700">
				{{ __("Started at {0}", [dayjs(spl.mulai_lembur).format("hh:mm a")]) }}
			</div>
		</div>
		<Button variant="solid" class="py-5 text-base" @click="bukaModal">
			<template #prefix>
				<FeatherIcon :name="sedangLembur ? 'stop-circle' : 'play-circle'" class="w-4" />
			</template>
			{{ sedangLembur ? __("End Overtime") : __("Start Overtime") }}
		</Button>
	</div>

	<ion-modal :is-open="modalTerbuka" :initial-breakpoint="1" :breakpoints="[0, 1]" @didDismiss="tutupModal">
		<div class="w-full flex flex-col items-center justify-center gap-5 p-4 mb-5">
			<div class="flex flex-col gap-1.5 mt-2 items-center">
				<div class="font-bold text-xl">{{ sedangLembur ? __("End Overtime") : __("Start Overtime") }}</div>
				<div class="font-medium text-gray-500 text-sm">{{ dayjs().format("D MMM, YYYY hh:mm a") }}</div>
			</div>

			<div class="flex flex-col items-center gap-1 text-center">
				<span v-if="s.locationStatus.value" class="font-medium text-gray-500 text-sm">{{ s.locationStatus.value }}</span>
				<span v-if="s.locationHelp.value" class="text-xs text-gray-500">{{ s.locationHelp.value }}</span>
				<button
					v-if="s.locationState.value === 'error'"
					@click="s.fetchLocation"
					class="mt-1 px-4 py-1.5 rounded-lg bg-gray-100 text-gray-700 text-sm font-medium"
				>
					🔄 {{ __("Coba Lagi") }}
				</button>
			</div>

			<div class="w-full flex flex-col items-center gap-2">
				<img
					v-if="s.photoPreview.value"
					:src="s.photoPreview.value"
					class="w-full max-w-xs rounded-lg border"
					style="max-height: 200px; object-fit: cover; transform: scaleX(-1)"
				/>
				<video
					v-show="s.cameraActive.value && !s.photoPreview.value"
					:ref="(el) => (s.videoRef.value = el)"
					autoplay
					playsinline
					class="w-full max-w-xs rounded-lg border"
					style="max-height: 200px; object-fit: cover; transform: scaleX(-1)"
				></video>
				<canvas :ref="(el) => (s.canvasRef.value = el)" style="display: none"></canvas>
				<div class="flex gap-2 w-full">
					<button
						v-if="!s.cameraActive.value && !s.photoPreview.value"
						@click="s.openCamera"
						class="w-full py-2 rounded-lg bg-gray-100 text-gray-700 text-sm font-medium"
					>
						📷 {{ __("Buka Kamera") }}
					</button>
					<button
						v-if="s.cameraActive.value && !s.photoPreview.value"
						@click="s.capturePhoto"
						class="w-full py-2 rounded-lg bg-blue-500 text-white text-sm font-medium"
					>
						📸 {{ __("Ambil Foto") }}
					</button>
					<button
						v-if="s.photoPreview.value"
						@click="s.retakePhoto"
						class="w-full py-2 rounded-lg bg-gray-100 text-gray-700 text-sm font-medium"
					>
						🔄 {{ __("Foto Ulang") }}
					</button>
				</div>
				<span v-if="s.photoStatus.value" class="text-xs text-gray-500 text-center">{{ s.photoStatus.value }}</span>
			</div>

			<Button
				:loading="mengirim"
				:disabled="!s.siap.value"
				variant="solid"
				class="w-full py-5 text-sm disabled:bg-gray-700"
				@click="kirim"
			>
				{{ sedangLembur ? __("Confirm End Overtime") : __("Confirm Start Overtime") }}
			</Button>
			<span v-if="s.petunjuk.value" class="text-xs text-gray-500 -mt-3">{{ s.petunjuk.value }}</span>
		</div>
	</ion-modal>
</template>

<script setup>
import { computed, inject, ref, onBeforeUnmount } from "vue"
import { IonModal } from "@ionic/vue"
import { Button, FeatherIcon, createResource, toast } from "frappe-ui"

import LemburIcon from "@/components/icons/LemburIcon.vue"
import { labelJam, lemburHariIni, reloadLembur } from "@/data/lembur"
import { useSelfieLokasi } from "@/composables/selfieLokasi"

const __ = inject("$translate")
const dayjs = inject("$dayjs")

const s = useSelfieLokasi()
const modalTerbuka = ref(false)

// SPL yang sedang berjalan diutamakan, lalu yang terdekat
const spl = computed(() => {
	const rows = lemburHariIni.data || []
	return rows.find((r) => r.status === "In Progress") || rows[0] || null
})
const sedangLembur = computed(() => spl.value?.status === "In Progress")

const mengirim = ref(false)

function bukaModal() {
	lemburHariIni.reload()
	s.reset()
	modalTerbuka.value = true
	s.fetchLocation()
}

function tutupModal() {
	s.stopCamera()
	modalTerbuka.value = false
}

function kirim() {
	const label = sedangLembur.value ? __("End overtime") : __("Start overtime")
	mengirim.value = true
	createResource({
		url: sedangLembur.value ? "hrms.xsha.lembur.selesai_lembur" : "hrms.xsha.lembur.mulai_lembur",
	}).submit(
		{
			name: spl.value.name,
			latitude: s.latitude.value,
			longitude: s.longitude.value,
			photo: s.photoData.value,
		},
		{
			onSuccess(data) {
				mengirim.value = false
				tutupModal()
				reloadLembur()
				const teks = data?.status === "Pending Confirmation"
					? __("{0} successful! {1} hrs counted, waiting for supervisor confirmation.", [label, data.jam_dihitung || 0])
					: __("{0} successful!", [label])
				toast({ title: __("Success"), text: teks, icon: "check-circle", position: "bottom-center", iconClasses: "text-green-500" })
			},
			onError(error) {
				mengirim.value = false
				const pesan = error?.messages?.length ? error.messages.join(" ") : error?.message
				toast({ title: __("Error"), text: pesan || __("{0} failed!", [label]), icon: "alert-circle", position: "bottom-center", iconClasses: "text-red-500", timeout: 8 })
			},
		}
	)
}

onBeforeUnmount(() => s.stopCamera())
</script>
