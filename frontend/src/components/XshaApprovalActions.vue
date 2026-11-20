<template>
	<!-- X-SHA: 2-level approval (Supervisor -> HR) for Leave, Shift and Attendance Requests.
	     See hrms/xsha/approval.py -->
	<div v-if="canAct" :class="containerClass">
		<div class="flex w-full flex-row items-center justify-between gap-3">
			<Button
				v-if="actions.data.can_reject"
				class="w-full py-5"
				variant="subtle"
				theme="red"
				:loading="busy === 'reject'"
				:disabled="Boolean(busy)"
				@click="run('reject')"
			>
				<template #prefix>
					<FeatherIcon name="x" class="w-4" />
				</template>
				{{ __("Reject") }}
			</Button>
			<Button
				v-if="actions.data.can_approve"
				class="w-full py-5"
				variant="solid"
				theme="green"
				:loading="busy === 'approve'"
				:disabled="Boolean(busy)"
				@click="run('approve')"
			>
				<template #prefix>
					<FeatherIcon name="check" class="w-4" />
				</template>
				{{ actions.data.stage === "hrd" ? __("Approve (HR)") : __("Approve") }}
			</Button>
		</div>
	</div>
	<div v-else-if="actions.data?.stage && showWaiting" :class="containerClass">
		<div class="w-full text-center text-sm text-gray-600">
			{{
				actions.data.stage === "hrd"
					? __("Waiting for HR approval")
					: __("Waiting for supervisor approval")
			}}
		</div>
	</div>
</template>

<script setup>
import { computed, inject, ref, watch } from "vue"
import { Button, FeatherIcon, createResource, toast } from "frappe-ui"

const __ = inject("$translate")

const API = "hrms.xsha.approval."

const props = defineProps({
	doctype: { type: String, required: true },
	name: { type: String, required: true },
	// reload actions when the document changes (e.g. after save)
	modified: { type: String, default: "" },
	containerClass: { type: String, default: "" },
	showWaiting: { type: Boolean, default: true },
})

const emit = defineEmits(["done"])
const busy = ref("")

const actions = createResource({
	url: API + "get_approval_actions",
	params: { doctype: props.doctype, name: props.name },
	auto: true,
})

watch(
	() => props.modified,
	() => actions.reload()
)

const canAct = computed(() => actions.data?.can_approve || actions.data?.can_reject)

function run(method) {
	busy.value = method
	createResource({ url: API + method }).submit(
		{ doctype: props.doctype, name: props.name },
		{
			onSuccess() {
				busy.value = ""
				toast({
					title: __("Success"),
					text: method === "approve" ? __("Approved successfully!") : __("Rejected successfully!"),
					icon: "check-circle",
					position: "bottom-center",
					iconClasses: "text-green-500",
				})
				actions.reload()
				emit("done")
			},
			onError(error) {
				busy.value = ""
				const message = error?.messages?.length ? error.messages.join(" ") : error?.message
				toast({
					title: __("Error"),
					text: message || __("Action failed!"),
					icon: "alert-circle",
					position: "bottom-center",
					iconClasses: "text-red-500",
					timeout: 8,
				})
			},
		}
	)
}
</script>
