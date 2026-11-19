<template>
	<ion-page>
		<ion-content :fullscreen="true">
			<FormView
				v-if="formFields.data"
				doctype="Overtime Request"
				v-model="pengajuan"
				:fields="formFields.data"
				@validateForm="validateForm"
			/>
		</ion-content>
	</ion-page>
</template>

<script setup>
import { IonPage, IonContent } from "@ionic/vue"
import { createResource } from "frappe-ui"
import { ref, inject, watch } from "vue"

import FormView from "@/components/FormView.vue"
import { reloadLembur } from "@/data/lembur"

const employee = inject("$employee")
const __ = inject("$translate")
const dayjs = inject("$dayjs")

// Karyawan hanya mengisi rencana. Status, atasan, kompensasi, SPL diisi lewat persetujuan.
const FIELD_PENGAJUAN = ["tanggal", "jam_mulai", "jam_selesai", "pekerjaan", "alasan"]

const pengajuan = ref({})

const formFields = createResource({
	url: "hrms.api.get_doctype_fields",
	params: { doctype: "Overtime Request" },
	auto: true,
	transform(data) {
		const fields = data.filter((field) => FIELD_PENGAJUAN.includes(field.fieldname))
		const tanggal = fields.find((f) => f.fieldname === "tanggal")
		if (tanggal) {
			tanggal.description = __("Can be requested on the same day. Overtime can only start after Supervisor and HR approval.")
		}
		const selesai = fields.find((f) => f.fieldname === "jam_selesai")
		if (selesai) selesai.description = __("Maximum 3 hours per day.")
		return fields
	},
})

watch(
	() => [pengajuan.value.tanggal, pengajuan.value.jam_mulai, pengajuan.value.jam_selesai],
	([tanggal]) => {
		const field = formFields.data?.find((f) => f.fieldname === "tanggal")
		if (!field) return
		field.error_message =
			tanggal && dayjs(tanggal).isBefore(dayjs(), "day")
				? __("Overtime Date cannot be in the past")
				: ""
	}
)

function validateForm() {
	pengajuan.value.employee = employee.data.name
	setTimeout(reloadLembur, 1500)
}
</script>
