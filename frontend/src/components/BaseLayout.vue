<template>
	<ion-page>
		<ion-header class="ion-no-border">
			<div class="w-full sm:w-96">
				<div class="flex flex-col bg-white shadow-sm p-4">
					<div class="flex flex-row justify-between items-center">
						<div class="flex flex-row items-center gap-2">
							<h2 class="text-xl font-bold text-gray-900">
								{{ props.pageTitle || __("X-PEOPLE") }}
							</h2>
						</div>
						<div class="flex flex-row items-center gap-3 ml-auto">
							<!-- X-Sha: muat ulang aplikasi (sekalian ambil versi terbaru) -->
							<button
								type="button"
								class="flex flex-col items-center"
								:disabled="memuatUlang"
								:aria-label="__('Muat ulang aplikasi')"
								@click="muatUlang"
							>
								<FeatherIcon
									name="refresh-cw"
									class="h-6 w-6"
									:class="{ 'animate-spin': memuatUlang }"
								/>
							</button>
							<router-link
								:to="{ name: 'Notifications' }"
								v-slot="{ navigate }"
								class="flex flex-col items-center"
							>
								<span class="relative inline-block" @click="navigate">
									<FeatherIcon name="bell" class="h-6 w-6" />
									<span
										v-if="unreadNotificationsCount.data"
										class="absolute top-0 right-0.5 inline-block w-2 h-2 bg-red-600 rounded-full border border-white"
									>
									</span>
								</span>
							</router-link>
							<router-link
								:to="{ name: 'Profile' }"
								class="flex flex-col items-center"
							>
								<Avatar
									:image="user.data.user_image"
									:label="user.data.first_name"
									size="xl"
								/>
							</router-link>
						</div>
					</div>
				</div>
			</div>
		</ion-header>

		<ion-content class="ion-no-padding">
			<div class="flex flex-col h-screen w-screen sm:w-96">
				<slot name="body"></slot>
			</div>
		</ion-content>
	</ion-page>
</template>

<script setup>
import { IonHeader, IonContent, IonPage } from "@ionic/vue"
import { FeatherIcon, Avatar } from "frappe-ui"

import { unreadNotificationsCount } from "@/data/notifications"

import { inject, ref } from "vue"

const user = inject("$user")

const memuatUlang = ref(false)

// Cek versi baru di server (service worker) maksimal 3 detik, lalu muat ulang penuh.
async function muatUlang() {
	if (memuatUlang.value) return
	memuatUlang.value = true
	try {
		if ("serviceWorker" in navigator) {
			const regs = await navigator.serviceWorker.getRegistrations()
			await Promise.race([
				Promise.allSettled(regs.map((r) => r.update())),
				new Promise((r) => setTimeout(r, 3000)),
			])
		}
	} catch (e) {
		// tetap muat ulang walau cek versi gagal (mis. sedang offline)
	}
	window.location.reload()
}

const props = defineProps({
	pageTitle: {
		type: String,
		required: false,
		default: "",
	},
})
</script>
