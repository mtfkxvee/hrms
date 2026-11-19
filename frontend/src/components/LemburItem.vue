<template>
	<ListItem
		:isTeamRequest="props.isTeamRequest"
		:employee="props.doc.employee"
		:employeeName="props.doc.employee_name"
	>
		<template #left>
			<LemburIcon class="h-5 w-5 text-gray-500" />
			<div class="flex flex-col items-start gap-1.5">
				<div class="text-base font-normal text-gray-800">
					{{ __("Overtime") }}
					<span v-if="props.doc.kompensasi" class="text-gray-500">&middot; {{ props.doc.kompensasi }}</span>
				</div>
				<div class="text-xs font-normal text-gray-500">
					<span>{{ labelTanggal(props.doc) }}</span>
					<span class="whitespace-pre"> &middot; </span>
					<span class="whitespace-nowrap">{{ labelJam(props.doc) }}</span>
					<template v-if="props.doc.status === 'Completed'">
						<span class="whitespace-pre"> &middot; </span>
						<span class="whitespace-nowrap">{{ __("{0} hrs", [props.doc.jam_dihitung || 0]) }}</span>
					</template>
				</div>
			</div>
		</template>
		<template #right>
			<Badge variant="outline" :theme="STATUS_WARNA[props.doc.status] || 'gray'" :label="props.doc.status" size="md" />
			<FeatherIcon name="chevron-right" class="h-5 w-5 text-gray-500" />
		</template>
	</ListItem>
</template>

<script setup>
import { Badge, FeatherIcon } from "frappe-ui"

import ListItem from "@/components/ListItem.vue"
import LemburIcon from "@/components/icons/LemburIcon.vue"
import { STATUS_WARNA, labelJam, labelTanggal } from "@/data/lembur"

const props = defineProps({
	doc: {
		type: Object,
	},
	isTeamRequest: {
		type: Boolean,
		default: false,
	},
	workflowStateField: {
		type: String,
		required: false,
	},
})
</script>
