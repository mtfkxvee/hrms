<template>
	<BaseLayout pageTitle="Attendance">
		<template #body>
			<div class="flex flex-col mt-7 mb-7 p-4 gap-7">
				<AttendanceCalendar />
				<div class="w-full">
					<router-link :to="{ name: 'AttendanceRequestFormView' }" v-slot="{ navigate }">
						<Button @click="navigate" variant="solid" class="w-full py-5 text-base">
							{{ __("Request Attendance") }}
						</Button>
					</router-link>
				</div>
				<div>
					<div class="text-lg text-gray-800 font-bold">{{ __("Recent Attendance Requests") }}</div>
					<RequestList
						:component="markRaw(AttendanceRequestItem)"
						:items="myAttendanceRequests?.data?.slice(0, 5)"
						:addListButton="true"
						:listButtonRoute="__('AttendanceRequestListView')"
					/>
				</div>
				<div>
					<div class="text-lg text-gray-800 font-bold">{{ __("Upcoming Shifts") }}</div>
					<RequestList
						:component="markRaw(ShiftAssignmentItem)"
						:items="upcomingShifts"
						:addListButton="true"
						listButtonRoute="ShiftAssignmentListView"
						:emptyStateMessage="__('You have no upcoming shifts')"
					/>
				</div>
				<div class="w-full">
					<router-link :to="{ name: 'ShiftRequestFormView' }" v-slot="{ navigate }">
						<Button @click="navigate" variant="solid" class="w-full py-5 text-base">
							{{ __("Request a Shift") }}
						</Button>
					</router-link>
				</div>
				<div>
					<div class="text-lg text-gray-800 font-bold">{{ __("Recent Shift Requests") }}</div>
					<RequestList
						:component="markRaw(ShiftRequestItem)"
						:items="myShiftRequests?.data?.slice(0, 5)"
						:addListButton="true"
						listButtonRoute="ShiftRequestListView"
					/>
				</div>

				<!-- X-Sha: Lembur dan saldo PJK -->
				<div class="flex flex-col gap-3">
					<div class="text-lg text-gray-800 font-bold">{{ __("Overtime") }}</div>
					<div class="flex flex-col bg-white rounded p-4 gap-1">
						<div class="flex flex-row items-center justify-between">
							<span class="text-base text-gray-700">{{ __("PJK Balance") }}</span>
							<span class="text-base font-semibold text-gray-900">
								{{ __("{0} / {1} hrs", [saldoPjk.data?.saldo || 0, saldoPjk.data?.batas || 9]) }}
							</span>
						</div>
						<div
							v-for="j in saldoPjk.data?.jadwal || []"
							:key="j.name"
							class="text-xs text-gray-500"
						>
							{{ __("Take {0} hrs: {1}, {2} - {3}", [j.jam_dihitung, dayjs(j.pjk_tanggal).format("ddd, D MMM"), jamPendek(j.pjk_jam_mulai), jamPendek(j.pjk_jam_selesai)]) }}
						</div>
						<div v-if="!(saldoPjk.data?.jadwal || []).length" class="text-xs text-gray-500">
							{{ __("Missed PJK schedules expire.") }}
						</div>
					</div>
					<router-link :to="{ name: 'OvertimeRequestFormView' }" v-slot="{ navigate }">
						<Button @click="navigate" variant="solid" class="w-full py-5 text-base">
							{{ __("Request Overtime") }}
						</Button>
					</router-link>
					<RequestList
						:component="markRaw(LemburItem)"
						:items="myLembur?.data?.slice(0, 5)"
						:addListButton="true"
						listButtonRoute="OvertimeRequestListView"
						:emptyStateMessage="__('You have no overtime requests')"
					/>
				</div>
			</div>
		</template>
	</BaseLayout>
</template>

<script setup>
import { computed, inject, markRaw } from "vue"
import { createResource } from "frappe-ui"

import BaseLayout from "@/components/BaseLayout.vue"
import AttendanceRequestItem from "@/components/AttendanceRequestItem.vue"
import ShiftRequestItem from "@/components/ShiftRequestItem.vue"
import ShiftAssignmentItem from "@/components/ShiftAssignmentItem.vue"
import RequestList from "@/components/RequestList.vue"
import AttendanceCalendar from "@/components/AttendanceCalendar.vue"
import LemburItem from "@/components/LemburItem.vue"
import { myLembur, saldoPjk, jamPendek } from "@/data/lembur"

import {
	getShiftDates,
	getTotalShiftDays,
	getShiftTiming,
	myAttendanceRequests,
	myShiftRequests,
} from "@/data/attendance"

const dayjs = inject("$dayjs")

const shifts = createResource({
	url: "hrms.api.get_shifts",
	auto: true,
	cache: "hrms:shifts",
	transform: (data) => {
		return data.map((assignment) => {
			assignment.doctype = "Shift Assignment"
			assignment.is_upcoming = !assignment.end_date || dayjs(assignment.end_date).isAfter(dayjs())
			assignment.shift_dates = getShiftDates(assignment)
			assignment.total_shift_days = getTotalShiftDays(assignment)
			assignment.shift_timing = getShiftTiming(assignment)
			return assignment
		})
	},
})

const upcomingShifts = computed(() => {
	const filteredShifts = shifts.data?.filter((shift) => shift.is_upcoming)

	// show only 5 upcoming shifts
	return filteredShifts?.slice(0, 5)
})
</script>
