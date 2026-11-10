<template>
	<ion-page>
		<ion-content class="ion-padding">
			<div class="flex flex-col h-screen w-screen">
				<div class="w-full sm:w-96">
					<header
						class="flex flex-row bg-white shadow-sm py-4 px-3 items-center border-b sticky top-0 z-10"
					>
						<Button variant="ghost" class="!pl-0 hover:bg-white" @click="router.back()">
							<FeatherIcon name="chevron-left" class="h-5 w-5" />
						</Button>
						<h2 class="text-xl font-semibold text-gray-900">{{ __("Edit Profil") }}</h2>
					</header>

					<div v-if="profile.loading && !profile.data" class="p-4 text-sm text-gray-500">
						{{ __("Memuat...") }}
					</div>

					<div v-else-if="profile.data" class="flex flex-col gap-5 p-4 pb-24">
						<p class="text-sm text-gray-500">
							{{
								__(
									"Nama, tanggal lahir, data pekerjaan, rekening, dan approver hanya bisa diubah oleh HR."
								)
							}}
						</p>

						<div
							v-for="section in profile.data.sections"
							:key="section.title"
							class="flex flex-col gap-4 bg-white rounded p-4"
						>
							<h3 class="text-base font-semibold text-gray-900">{{ section.title }}</h3>
							<FormControl
								v-for="field in section.fields"
								:key="field.fieldname"
								:type="controlType(field)"
								:label="field.label"
								:options="selectOptions(field)"
								v-model="form[field.fieldname]"
							/>
						</div>

						<Button
							variant="solid"
							class="w-full py-5 text-sm"
							:loading="save.loading"
							:disabled="!isDirty"
							@click="submit"
						>
							{{ __("Simpan") }}
						</Button>
					</div>
				</div>
			</div>
		</ion-content>
	</ion-page>
</template>

<script setup>
import { computed, inject, reactive } from "vue"
import { useRouter } from "vue-router"
import { IonPage, IonContent } from "@ionic/vue"
import { FeatherIcon, FormControl, createResource, toast } from "frappe-ui"

const __ = inject("$translate")
const router = useRouter()

const form = reactive({})
const original = reactive({})

const profile = createResource({
	url: "hrms.xsha.profile.get_my_profile",
	auto: true,
	onSuccess(data) {
		for (const section of data.sections) {
			for (const field of section.fields) {
				form[field.fieldname] = field.value || ""
				original[field.fieldname] = field.value || ""
			}
		}
	},
})

const changes = computed(() => {
	const out = {}
	for (const key of Object.keys(form)) {
		if ((form[key] || "") !== (original[key] || "")) out[key] = form[key]
	}
	return out
})

const isDirty = computed(() => Object.keys(changes.value).length > 0)

function controlType(field) {
	if (field.fieldtype === "Select") return "select"
	if (["Small Text", "Text", "Long Text"].includes(field.fieldtype)) return "textarea"
	if (["cell_number", "emergency_phone_number"].includes(field.fieldname)) return "tel"
	if (field.fieldname === "personal_email") return "email"
	return "text"
}

function selectOptions(field) {
	if (field.fieldtype !== "Select") return undefined
	return [{ label: "-", value: "" }, ...field.options.map((o) => ({ label: __(o), value: o }))]
}

const save = createResource({
	url: "hrms.xsha.profile.update_my_profile",
})

function submit() {
	save.submit(
		{ data: changes.value },
		{
			onSuccess() {
				Object.assign(original, { ...form })
				toast({
					title: __("Tersimpan"),
					text: __("Profil berhasil diperbarui"),
					icon: "check-circle",
					position: "bottom-center",
					iconClasses: "text-green-500",
				})
				router.back()
			},
			onError(error) {
				const messages = error.messages?.length ? error.messages : [error.message]
				toast({
					title: __("Gagal menyimpan"),
					text: messages.join(" "),
					icon: "alert-circle",
					position: "bottom-center",
					iconClasses: "text-red-500",
				})
			},
		}
	)
}
</script>
