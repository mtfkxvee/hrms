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
				<span v-if="offline.mulai" class="text-orange-600">({{ __("belum terkirim") }})</span>
			</div>
		</div>
		<div v-if="offline.selesai" class="text-sm text-orange-600">
			{{ __("Selesai lembur jam {0} tersimpan di HP, dikirim otomatis saat server kembali normal.", [dayjs(offline.selesai.waktu_ms).format("HH:mm")]) }}
		</div>
		<Button v-else variant="solid" class="py-5 text-base" @click="bukaModal">
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
					style="max-height: 200px; object-fit: cover"
				/>
				<!-- X-Sha: selfie lewat aplikasi kamera bawaan HP -->
				<input
					:ref="(el) => (s.inputFotoRef.value = el)"
					type="file"
					accept="image/*"
					capture="user"
					style="display: none"
					@change="s.onFotoDipilih"
				/>
				<div class="flex gap-2 w-full">
					<button
						v-if="!s.photoPreview.value"
						@click="s.ambilFoto"
						:disabled="s.memprosesFoto.value"
						class="w-full py-2 rounded-lg bg-blue-500 text-white text-sm font-medium disabled:opacity-60"
					>
						📷 {{ s.memprosesFoto.value ? __("Memproses foto...") : __("Ambil Foto") }}
					</button>
					<button
						v-else
						@click="s.ambilFoto"
						:disabled="s.memprosesFoto.value"
						class="w-full py-2 rounded-lg bg-gray-100 text-gray-700 text-sm font-medium disabled:opacity-60"
					>
						🔄 {{ s.memprosesFoto.value ? __("Memproses foto...") : __("Foto Ulang") }}
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
import { Button, FeatherIcon, toast } from "frappe-ui"

import LemburIcon from "@/components/icons/LemburIcon.vue"
import { labelJam, lemburHariIni, reloadLembur } from "@/data/lembur"
import { useSelfieLokasi } from "@/composables/selfieLokasi"
import { antrean, kirimAtauSimpan, saatTerkirim } from "@/offline/antrean"

const __ = inject("$translate")
const dayjs = inject("$dayjs")

const s = useSelfieLokasi()
const modalTerbuka = ref(false)

// Mulai/Selesai Lembur yang masih di antrean offline, per SPL
function offlineUntuk(name) {
	const items = antrean.items.filter((i) => i.jenis === "lembur" && i.status === "menunggu" && i.params.name === name)
	return {
		mulai: items.find((i) => i.params.aksi === "mulai") || null,
		selesai: items.find((i) => i.params.aksi === "selesai") || null,
	}
}

// SPL yang sedang berjalan diutamakan, lalu yang terdekat. Mulai yang belum terkirim
// dianggap sudah berjalan supaya tombol berikutnya adalah Selesai.
const spl = computed(() => {
	const rows = (lemburHariIni.data || []).map((r) => {
		const o = offlineUntuk(r.name)
		if (r.status === "Approved" && o.mulai) {
			return { ...r, status: "In Progress", mulai_lembur: dayjs(o.mulai.waktu_ms).format("YYYY-MM-DD HH:mm:ss") }
		}
		return r
	})
	return rows.find((r) => r.status === "In Progress") || rows[0] || null
})
const offline = computed(() => (spl.value ? offlineUntuk(spl.value.name) : { mulai: null, selesai: null }))
const sedangLembur = computed(() => spl.value?.status === "In Progress")

const mengirim = ref(false)

function bukaModal() {
	lemburHariIni.reload()
	s.reset()
	modalTerbuka.value = true
	s.fetchLocation()
}

function tutupModal() {
	modalTerbuka.value = false
}

async function kirim() {
	const selesai = sedangLembur.value
	const label = selesai ? __("End overtime") : __("Start overtime")
	mengirim.value = true
	let hasil
	try {
		hasil = await kirimAtauSimpan(
			"lembur",
			selesai ? "hrms.xsha.lembur.selesai_lembur" : "hrms.xsha.lembur.mulai_lembur",
			{
				name: spl.value.name,
				latitude: s.latitude.value,
				longitude: s.longitude.value,
				photo: s.photoData.value,
			},
			{ aksi: selesai ? "selesai" : "mulai" }
		)
	} catch (error) {
		hasil = { pesan: error?.message }
	} finally {
		mengirim.value = false
	}

	if (hasil.ok) {
		tutupModal()
		reloadLembur()
		const data = hasil.data
		const teks = data?.status === "Pending Confirmation"
			? __("{0} successful! {1} hrs counted, waiting for supervisor confirmation.", [label, data.jam_dihitung || 0])
			: __("{0} successful!", [label])
		toast({ title: __("Success"), text: teks, icon: "check-circle", position: "bottom-center", iconClasses: "text-green-500" })
		return
	}
	if (hasil.tersimpan) {
		tutupModal()
		toast({
			title: __("Tersimpan di HP"),
			text: __("Server sedang tidak bisa dihubungi. {0} jam {1} sudah tersimpan dan akan dikirim otomatis saat server kembali normal.", [label, dayjs(hasil.waktu_ms).format("HH:mm")]),
			icon: "clock",
			position: "bottom-center",
			iconClasses: "text-orange-500",
			timeout: 10,
		})
		return
	}
	toast({ title: __("Error"), text: hasil.pesan || __("{0} failed!", [label]), icon: "alert-circle", position: "bottom-center", iconClasses: "text-red-500", timeout: 8 })
}

const hentikanPendengarAntrean = saatTerkirim((item) => {
	if (item.jenis === "lembur") reloadLembur()
})

onBeforeUnmount(() => hentikanPendengarAntrean())
</script>
