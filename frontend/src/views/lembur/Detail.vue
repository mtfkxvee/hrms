<template>
	<ion-page>
		<ion-content :fullscreen="true">
			<div class="flex flex-col h-screen w-screen">
				<div class="w-full sm:w-96">
					<header
						class="flex flex-row bg-white shadow-sm py-4 px-3 items-center border-b sticky top-0 z-10"
					>
						<Button variant="ghost" class="!pl-0 hover:bg-white" @click="router.back()">
							<FeatherIcon name="chevron-left" class="h-5 w-5" />
						</Button>
						<h2 class="text-xl font-semibold text-gray-900">{{ props.id }}</h2>
					</header>
					<LemburDetail :name="props.id" />
				</div>
			</div>
		</ion-content>
	</ion-page>
</template>

<script setup>
import { IonPage, IonContent } from "@ionic/vue"
import { useRouter } from "vue-router"
import { Button, FeatherIcon } from "frappe-ui"

import LemburDetail from "@/components/LemburDetail.vue"

const router = useRouter()
const props = defineProps({
	id: { type: String, required: true },
})
</script>
