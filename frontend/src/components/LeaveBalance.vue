<template>
	<div class="flex flex-col w-full">
		<div class="flex flex-row justify-between items-center px-4">
			<div class="text-lg text-gray-800 font-bold">{{ __("Leave Balance") }} </div>
			<router-link
				:to="{ name: 'LeaveApplicationListView' }"
				v-slot="{ navigate }"
				v-if="leaveBalance.data"
			>
				<div
					@click="navigate"
					class="text-sm text-gray-800 font-semibold cursor-pointer underline underline-offset-2"
				>
					{{ __("View Leave History") }}
				</div>
			</router-link>
		</div>

		<!-- Leave Balance Dashboard -->
		<div
			class="flex flex-row gap-4 overflow-x-auto py-2 mt-3"
			v-if="cards.length"
		>
			<div
				v-for="(card, index) in cards"
				:key="card.leave_type"
				class="flex flex-col bg-white border-none rounded-lg drop-shadow-md gap-2 p-4 items-start first:ml-4"
			>
				<!-- X-SHA: cuti tanpa batas (jatah >= 365) hanya tampil jumlah terpakai -->
				<template v-if="card.unlimited">
					<div class="text-gray-800 font-bold text-2xl leading-[4.5rem]">
						{{ card.used === 1 ? __("1 day") : __("{0} days", [card.used]) }}
					</div>
					<div class="text-gray-600 font-normal text-sm w-24 leading-4">
						{{ __("{0} used", [__(card.leave_type, null, "Leave Type")]) }}
					</div>
				</template>
				<template v-else>
					<SemicircleChart
						:percentage="card.balance_percentage"
						:colorClass="getChartColor(index)"
					/>
					<div class="text-gray-800 font-bold text-base">
						{{ `${card.balance_leaves}/${card.allocated_leaves}` }}
					</div>
					<div class="text-gray-600 font-normal text-sm w-24 leading-4">
						{{ __("{0} balance", [__(card.leave_type, null, "Leave Type")]) }}
					</div>
				</template>
			</div>
		</div>

		<EmptyState
			:message="leaveBalance.data ? __('No leaves used yet') : __('You have no leaves allocated')"
			v-else
		/>
	</div>
</template>

<script setup>
import SemicircleChart from "@/components/SemicircleChart.vue"
import { leaveBalance, isUnlimitedLeave } from "@/data/leaves"
import { computed, inject } from "vue"

const __ = inject("$translate")
// X-SHA: Cuti Tahunan (berjatah) selalu tampil sisa/jatah; cuti tanpa batas (SAKIT, CUTI ISTIMEWA)
// hanya tampil kalau sudah terpakai, berupa jumlah hari terpakai.
const cards = computed(() =>
	Object.entries(leaveBalance.data || {})
		.map(([leave_type, allocation]) => ({
			leave_type,
			...allocation,
			unlimited: isUnlimitedLeave(allocation),
			used: Math.max(0, (allocation.allocated_leaves || 0) - (allocation.balance_leaves || 0)),
		}))
		.filter((card) => !card.unlimited || card.used > 0)
		.sort((a, b) => Number(a.unlimited) - Number(b.unlimited))
)

const getChartColor = (index) => {
	// note: tw colors - rose-400, pink-400 & purple-500 of the old frappeui palette #918ef5
	const chartColors = ["text-[#fb7185]", "text-[#f472b6]", "text-[#918ef5]"]
	return chartColors[index % chartColors.length]
}
</script>
