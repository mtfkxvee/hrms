<template>
	<!-- X-Sha mode offline: data yang tersimpan di HP dan belum sampai ke server -->
	<div v-if="antrean.items.length" class="flex flex-col bg-orange-50 border border-orange-200 rounded w-full py-4 px-4 gap-3">
		<div class="flex flex-row items-start gap-2">
			<FeatherIcon name="cloud-off" class="h-5 w-5 text-orange-600 shrink-0 mt-0.5" />
			<div class="flex flex-col gap-1">
				<h3 class="text-base font-bold text-gray-900">
					{{ __("{0} data belum terkirim", [antrean.items.length]) }}
				</h3>
				<p class="text-sm text-gray-700">{{ keterangan }}</p>
			</div>
		</div>

		<div class="flex flex-col gap-2">
			<div
				v-for="item in antrean.items"
				:key="item.id"
				class="flex flex-row items-start justify-between gap-2 bg-white rounded px-3 py-2"
			>
				<div class="flex flex-col">
					<span class="text-sm font-medium text-gray-900">{{ judul(item) }}</span>
					<span class="text-xs text-gray-500">{{ dayjs(item.waktu_ms).format("ddd, D MMM YYYY HH:mm") }}</span>
					<span v-if="item.status === 'ditolak'" class="text-xs text-red-600 mt-1">
						{{ __("Ditolak server: {0}", [item.pesan]) }}
					</span>
				</div>
				<button
					v-if="item.status === 'ditolak'"
					class="text-xs text-gray-600 underline shrink-0"
					@click="hapus(item)"
				>
					{{ __("Hapus") }}
				</button>
				<span v-else class="text-xs text-orange-600 shrink-0">{{ __("Menunggu") }}</span>
			</div>
		</div>

		<Button
			v-if="adaMenunggu && antrean.kondisi !== 'perlu_login'"
			:loading="antrean.mengirim"
			class="py-4"
			@click="kirimSemua"
		>
			<template #prefix><FeatherIcon name="refresh-cw" class="w-4" /></template>
			{{ __("Kirim sekarang") }}
		</Button>
		<Button v-if="antrean.kondisi === 'perlu_login'" variant="solid" class="py-4" @click="loginUlang">
			{{ __("Login ulang untuk mengirim") }}
		</Button>
	</div>
</template>

<script setup>
import { computed, inject } from "vue"
import { useRouter } from "vue-router"
import { Button, FeatherIcon } from "frappe-ui"

import { antrean, buangItem, itemMenunggu, kirimSemua } from "@/offline/antrean"

const __ = inject("$translate")
const dayjs = inject("$dayjs")
const router = useRouter()

const adaMenunggu = computed(() => itemMenunggu().length > 0)

const keterangan = computed(() => {
	if (antrean.kondisi === "perlu_login") {
		return __("Sesi login habis. Login ulang dengan akun yang sama, data akan dikirim otomatis.")
	}
	if (antrean.mengirim) return __("Sedang mengirim ke server...")
	if (adaMenunggu.value) {
		return __("Server belum bisa dihubungi. Data aman di HP ini dan dikirim otomatis saat server kembali normal. Jangan hapus data browser/aplikasi.")
	}
	return __("Data di bawah ditolak server. Ajukan koreksi lewat Attendance Request jika perlu, lalu hapus dari daftar.")
})

function judul(item) {
	if (item.jenis === "checkin") return item.params.log_type === "IN" ? __("Check In") : __("Check Out")
	if (item.jenis === "lembur") {
		const aksi = item.params.aksi === "mulai" ? __("Start Overtime") : __("End Overtime")
		return `${aksi} · ${item.params.name}`
	}
	return item.jenis
}

async function hapus(item) {
	if (!window.confirm(__("Hapus data ini dari HP? Data tidak akan dikirim ke server."))) return
	await buangItem(item.id)
}

function loginUlang() {
	// antrean tetap tersimpan per akun dan dikirim lagi setelah login dengan akun yang sama
	router.push({ name: "Login" })
}
</script>
