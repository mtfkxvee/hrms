<template>
	<ion-page>
		<ion-content :fullscreen="true">
			<div class="flex flex-col h-screen w-screen">
				<div class="w-full sm:w-96">
					<header
						class="flex flex-row bg-white shadow-sm py-4 px-3 items-center justify-between border-b sticky top-0 z-10"
					>
						<div class="flex flex-row items-center">
							<Button variant="ghost" class="!pl-0 hover:bg-white" @click="router.back()">
								<FeatherIcon name="chevron-left" class="h-5 w-5" />
							</Button>
							<h2 class="text-xl font-semibold text-gray-900">{{ __("Overtime History") }}</h2>
						</div>
						<router-link :to="{ name: 'OvertimeRequestFormView' }" v-slot="{ navigate }">
							<Button variant="solid" @click="navigate">
								<template #prefix><FeatherIcon name="plus" class="w-4" /></template>
								{{ __("New") }}
							</Button>
						</router-link>
					</header>

					<div class="flex flex-col gap-4 p-4">
						<TabButtons :buttons="TABS" v-model="tab" />
						<div class="flex flex-row flex-wrap gap-2">
							<button
								v-for="s in STATUS_FILTER"
								:key="s"
								class="px-3 py-1 rounded-full border text-xs"
								:class="status === s ? 'bg-gray-900 text-white border-gray-900' : 'bg-white text-gray-600'"
								@click="status = status === s ? '' : s"
							>
								{{ s }}
							</button>
						</div>
						<div v-if="daftar.loading && !items.length" class="text-sm text-gray-500 text-center">
							{{ __("Loading...") }}
						</div>
						<div v-else-if="items.length" class="flex flex-col bg-white rounded overflow-auto">
							<router-link
								v-for="row in items"
								:key="row.name"
								:to="{ name: 'OvertimeRequestDetailView', params: { id: row.name } }"
								class="flex flex-row p-3.5 items-center justify-between border-b"
							>
								<LemburItem :doc="row" :isTeamRequest="tab === 'tim'" />
							</router-link>
						</div>
						<EmptyState v-else :message="__('You have no overtime requests')" />
					</div>
				</div>
			</div>
		</ion-content>
	</ion-page>
</template>

<script setup>
import { IonPage, IonContent } from "@ionic/vue"
import { computed, inject, ref, watch } from "vue"
import { useRouter } from "vue-router"
import { Button, FeatherIcon, createResource } from "frappe-ui"

import TabButtons from "@/components/TabButtons.vue"
import LemburItem from "@/components/LemburItem.vue"
import EmptyState from "@/components/EmptyState.vue"

const __ = inject("$translate")
const router = useRouter()

const TABS = [
	{ key: "saya", label: "My Overtime" },
	{ key: "tim", label: "Team Requests" },
]
const STATUS_FILTER = ["Pending Supervisor", "Pending HR", "Approved", "Pending Confirmation", "Completed", "Rejected"]

const tab = ref("saya")
const status = ref("")

const daftar = createResource({
	url: "hrms.xsha.lembur.get_lembur_list",
	params: { limit: 100 },
	auto: true,
})

watch(tab, (t) => {
	daftar.submit({ for_approval: t === "tim" ? 1 : 0, limit: 100 })
})

const items = computed(() => {
	const rows = (daftar.data || []).map((r) => ({ ...r, doctype: "Overtime Request" }))
	return status.value ? rows.filter((r) => r.status === status.value) : rows
})
</script>
