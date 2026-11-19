<template>
	<div class="bg-white w-full flex flex-col" :class="props.inModal ? 'max-h-[calc(100vh-5rem)]' : ''">
		<div
			v-if="props.inModal"
			class="w-full flex flex-row gap-2 pt-8 pb-5 border-b justify-center items-center sticky top-0 z-[100] bg-white"
		>
			<span class="text-gray-900 font-bold text-lg text-center">{{ __("Overtime Request") }}</span>
			<FeatherIcon name="external-link" class="h-4 w-4 text-gray-500 cursor-pointer" @click="bukaHalaman" />
		</div>

		<div v-if="!doc.data" class="p-6 text-center text-sm text-gray-500">{{ __("Loading...") }}</div>

		<div v-else class="w-full p-4 overflow-auto flex flex-col gap-4">
			<div class="flex flex-row items-center justify-between">
				<div class="text-gray-600 text-base">{{ __("Status") }}</div>
				<Badge variant="outline" :theme="STATUS_WARNA[d.status] || 'gray'" :label="d.status" size="md" />
			</div>
			<div v-for="row in rows" :key="row.label" :class="row.panjang ? 'flex flex-col gap-1' : 'flex flex-row justify-between gap-3'">
				<div class="text-gray-600 text-base">{{ row.label }}</div>
				<div class="text-gray-900 text-base" :class="row.panjang ? '' : 'text-right'">{{ row.value }}</div>
			</div>

			<div v-if="d.saldo_pjk_penuh" class="rounded bg-yellow-50 text-yellow-800 text-sm p-3">
				{{ __("This employee's PJK balance would exceed 9 hours. HR can reject it, or the HR Manager can approve it as Paid Overtime.") }}
			</div>
			<div v-if="d.status === 'Rejected' && d.alasan_penolakan" class="rounded bg-red-50 text-red-800 text-sm p-3">
				{{ __("Rejected: {0}", [d.alasan_penolakan]) }}
			</div>

			<!-- Atasan: pilih kompensasi -->
			<div v-if="info.data?.bisa_setujui_atasan && !modeTolak" class="flex flex-col gap-3 border-t pt-4">
				<div class="text-base font-semibold text-gray-900">{{ __("Compensation") }}</div>
				<div class="flex flex-row gap-2">
					<button
						v-for="opsi in ['PJK', 'Paid Overtime']"
						:key="opsi"
						class="flex-1 py-2.5 rounded-lg border text-sm font-medium"
						:class="kompensasi === opsi ? 'bg-gray-900 text-white border-gray-900' : 'bg-white text-gray-700'"
						@click="kompensasi = opsi"
					>
						{{ opsi }}
					</button>
				</div>
				<div v-if="info.data?.saldo_pjk" class="text-xs text-gray-500">
					{{ __("Employee PJK balance: {0} hrs (+{1} hrs in process), limit {2} hrs", [info.data.saldo_pjk.saldo, info.data.saldo_pjk.rencana, info.data.saldo_pjk.batas]) }}
				</div>
				<template v-if="kompensasi === 'PJK'">
					<label class="text-sm text-gray-600">{{ __("PJK Date (leave early)") }}</label>
					<input type="date" v-model="pjkTanggal" :min="minPjk" class="w-full rounded border-gray-300 text-base" />
					<div class="flex flex-row gap-2">
						<div class="flex-1 flex flex-col gap-1">
							<label class="text-sm text-gray-600">{{ __("From Time") }}</label>
							<input type="time" v-model="pjkMulai" class="w-full rounded border-gray-300 text-base" />
						</div>
						<div class="flex-1 flex flex-col gap-1">
							<label class="text-sm text-gray-600">{{ __("To Time") }}</label>
							<input type="time" v-model="pjkSelesai" class="w-full rounded border-gray-300 text-base" />
						</div>
					</div>
				</template>
			</div>

			<!-- Konfirmasi: karyawan lupa menekan Selesai -->
			<div v-if="info.data?.bisa_konfirmasi && d.status === 'In Progress' && !modeTolak" class="flex flex-col gap-1 border-t pt-4">
				<label class="text-sm text-gray-600">{{ __("The employee has not ended the overtime. Enter the end time:") }}</label>
				<input type="time" v-model="jamSelesaiManual" class="w-full rounded border-gray-300 text-base" />
			</div>

			<!-- Alasan penolakan -->
			<div v-if="modeTolak" class="flex flex-col gap-2 border-t pt-4">
				<label class="text-sm text-gray-600">{{ __("Rejection Reason") }}</label>
				<textarea v-model="alasanTolak" rows="3" class="w-full rounded border-gray-300 text-base"></textarea>
			</div>
		</div>

		<!-- Tombol aksi -->
		<div v-if="doc.data && adaAksi" class="flex flex-col w-full gap-3 sticky bottom-0 border-t z-[100] p-4 bg-white">
			<template v-if="modeTolak">
				<div class="flex flex-row gap-3">
					<Button class="w-full py-5" variant="subtle" @click="modeTolak = false">{{ __("Back") }}</Button>
					<Button class="w-full py-5" variant="solid" theme="red" :loading="aksiLoading" @click="kirim('tolak', { alasan: alasanTolak })">
						{{ __("Reject") }}
					</Button>
				</div>
			</template>
			<template v-else>
				<div v-if="info.data?.bisa_tolak || bisaSetujui" class="flex flex-row gap-3">
					<Button v-if="info.data?.bisa_tolak" class="w-full py-5" variant="subtle" theme="red" @click="modeTolak = true">
						<template #prefix><FeatherIcon name="x" class="w-4" /></template>
						{{ __("Reject") }}
					</Button>
					<Button v-if="bisaSetujui" class="w-full py-5" variant="solid" theme="green" :loading="aksiLoading" @click="setujui">
						<template #prefix><FeatherIcon name="check" class="w-4" /></template>
						{{ __("Approve") }}
					</Button>
				</div>
				<Button
					v-if="info.data?.bisa_ubah_ke_berbayar && d.kompensasi === 'PJK'"
					class="w-full py-5"
					variant="subtle"
					:loading="aksiLoading"
					@click="kirim('setujui_hrd', { ubah_ke_berbayar: 1 })"
				>
					{{ __("Approve as Paid Overtime") }}
				</Button>
				<Button v-if="info.data?.bisa_konfirmasi" class="w-full py-5" variant="solid" :loading="aksiLoading" @click="konfirmasi">
					{{ __("Confirm Hours") }}
				</Button>
				<Button v-if="info.data?.bisa_batalkan" class="w-full py-5" variant="subtle" theme="red" :loading="aksiLoading" @click="batalkan">
					{{ yakinBatal ? __("Tap again to cancel") : __("Cancel Request") }}
				</Button>
			</template>
		</div>
	</div>
</template>

<script setup>
import { computed, inject, ref, watch } from "vue"
import { useRouter } from "vue-router"
import { modalController } from "@ionic/vue"
import { Badge, Button, FeatherIcon, createResource, toast } from "frappe-ui"

import { LEMBUR_DOCTYPE, STATUS_WARNA, jamPendek, reloadLembur } from "@/data/lembur"

const __ = inject("$translate")
const dayjs = inject("$dayjs")
const router = useRouter()

const props = defineProps({
	name: { type: String, required: true },
	inModal: { type: Boolean, default: false },
})

const API = "hrms.xsha.lembur."
const kompensasi = ref("")
const pjkTanggal = ref("")
const pjkMulai = ref("")
const pjkSelesai = ref("")
const jamSelesaiManual = ref("")
const modeTolak = ref(false)
const alasanTolak = ref("")
const yakinBatal = ref(false)

const doc = createResource({
	url: "frappe.client.get",
	params: { doctype: LEMBUR_DOCTYPE, name: props.name },
	auto: true,
})
const info = createResource({
	url: API + "get_info_persetujuan",
	params: { name: props.name },
	auto: true,
})
const aksiLoading = ref(false)

const d = computed(() => doc.data || {})
const formatTgl = (v) => (v ? dayjs(v).format("ddd, D MMM YYYY") : "")
const formatWaktu = (v) => (v ? dayjs(v).format("D MMM, HH.mm") : "")
const minPjk = computed(() => (d.value.tanggal ? dayjs(d.value.tanggal).add(1, "day").format("YYYY-MM-DD") : ""))

watch(
	() => doc.data,
	(v) => {
		if (v && !kompensasi.value) kompensasi.value = v.kompensasi || ""
	}
)

const rows = computed(() => {
	const r = []
	const add = (label, value, panjang = false) => value && r.push({ label, value, panjang })
	add(__("Employee"), d.value.employee_name)
	add(__("Date"), formatTgl(d.value.tanggal))
	add(__("Planned Hours"), d.value.jam_mulai && `${jamPendek(d.value.jam_mulai)} - ${jamPendek(d.value.jam_selesai)} (${d.value.durasi_rencana} hrs)`)
	add(__("Work to Do"), d.value.pekerjaan, true)
	add(__("Reason"), d.value.alasan, true)
	add(__("Supervisor"), d.value.atasan_name || d.value.atasan)
	add(__("Compensation"), d.value.kompensasi)
	if (d.value.kompensasi === "PJK" && d.value.pjk_tanggal)
		add(__("PJK Schedule"), `${formatTgl(d.value.pjk_tanggal)}, ${jamPendek(d.value.pjk_jam_mulai)} - ${jamPendek(d.value.pjk_jam_selesai)}`)
	add(__("SPL Number"), d.value.nomor_spl)
	add(__("Overtime Started"), formatWaktu(d.value.mulai_lembur))
	add(__("Overtime Ended"), formatWaktu(d.value.selesai_lembur))
	if (d.value.selesai_lembur) add(__("Counted Hours"), __("{0} hrs ({1} actual minutes)", [d.value.jam_dihitung || 0, d.value.menit_realisasi || 0]))
	if (d.value.tanggal_merah) add(__("Public Holiday"), __("Yes"))
	add(__("PJK Status"), d.value.status_pjk)
	return r
})

const bisaSetujui = computed(() => info.data?.bisa_setujui_atasan || info.data?.bisa_setujui_hrd)
const adaAksi = computed(
	() =>
		info.data &&
		(info.data.bisa_setujui_atasan ||
			info.data.bisa_setujui_hrd ||
			info.data.bisa_tolak ||
			info.data.bisa_konfirmasi ||
			info.data.bisa_batalkan)
)

function kirim(method, args) {
	if (method === "tolak" && !alasanTolak.value.trim()) {
		toast({ title: __("Error"), text: __("Please enter a rejection reason."), icon: "alert-circle", position: "bottom-center", iconClasses: "text-red-500" })
		return
	}
	aksiLoading.value = true
	createResource({ url: API + method }).submit(
		{ name: props.name, ...args },
		{
			onSuccess() {
				aksiLoading.value = false
				toast({ title: __("Success"), text: __("Overtime Request updated successfully!"), icon: "check-circle", position: "bottom-center", iconClasses: "text-green-500" })
				modeTolak.value = false
				yakinBatal.value = false
				doc.reload()
				info.reload()
				reloadLembur()
			},
			onError(error) {
				aksiLoading.value = false
				const pesan = error?.messages?.length ? error.messages.join(" ") : error?.message
				toast({ title: __("Error"), text: pesan || __("Action failed!"), icon: "alert-circle", position: "bottom-center", iconClasses: "text-red-500", timeout: 8 })
			},
		}
	)
}

function setujui() {
	if (info.data?.bisa_setujui_atasan) {
		kirim("setujui_atasan", {
			kompensasi: kompensasi.value,
			pjk_tanggal: kompensasi.value === "PJK" ? pjkTanggal.value : null,
			pjk_jam_mulai: kompensasi.value === "PJK" ? pjkMulai.value : null,
			pjk_jam_selesai: kompensasi.value === "PJK" ? pjkSelesai.value : null,
		})
	} else {
		kirim("setujui_hrd", {})
	}
}

function konfirmasi() {
	kirim("konfirmasi", d.value.status === "In Progress" ? { jam_selesai_manual: jamSelesaiManual.value } : {})
}

function batalkan() {
	if (!yakinBatal.value) {
		yakinBatal.value = true
		return
	}
	kirim("batalkan", {})
}

function bukaHalaman() {
	modalController.dismiss()
	router.push({ name: "OvertimeRequestDetailView", params: { id: props.name } })
}
</script>
