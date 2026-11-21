<template>
	<ion-page>
		<ion-content class="ion-padding">
			<div class="flex h-screen w-screen flex-col justify-center bg-white">
				<div class="flex flex-col mx-auto gap-3 items-center">
					<img :src="'/assets/hrms/images/x-people-logo-xp-w1.png'" alt="X-PEOPLE" class="h-20 w-20" />
					<div class="text-3xl font-semibold text-gray-900 text-center">
						{{ __("Login to X-PEOPLE") }}
					</div>
				</div>

				<div class="mx-auto mt-10 w-full px-8 sm:w-96">
					<form v-if="!user_pass_login_disabled.data" class="flex flex-col space-y-4" @submit.prevent="submit">
						<Input
							:label="__('Email')"
							:placeholder="__('johndoe@mail.com')"
							v-model="email"
							type="text"
							autocomplete="username"
						/>
						<!-- X-SHA: ikon mata untuk melihat / menyembunyikan password yang diketik -->
						<div class="relative">
							<Input
								:label="__('Password')"
								:type="showPassword ? 'text' : 'password'"
								placeholder="••••••"
								v-model="password"
								autocomplete="current-password"
								inputClass="pr-10"
							/>
							<button
								type="button"
								class="absolute right-0 bottom-0 flex h-7 items-center px-2.5 text-gray-500"
								:aria-label="showPassword ? __('Hide password') : __('Show password')"
								@mousedown.prevent
								@click="showPassword = !showPassword"
							>
								<FeatherIcon :name="showPassword ? 'eye-off' : 'eye'" class="h-4 w-4" />
							</button>
						</div>
						<!-- X-SHA: lupa password, kirim link reset ke email (fitur bawaan ERP) -->
						<div class="flex justify-end">
							<button
								type="button"
								class="text-sm text-gray-600 underline underline-offset-2"
								@click="openForgotPassword"
							>
								{{ __("Forgot Password?") }}
							</button>
						</div>
						<ErrorMessage :message="errorMessage" />
						<Button
							:loading="session.login.loading"
							variant="solid"
							class="disabled:bg-gray-700 disabled:text-white !mt-6"
						>
							{{ __("Login") }}
						</Button>
					</form>

					<!-- X-SHA: login dengan Google dihilangkan dari X-PEOPLE; login hanya pakai email + password -->

					<div v-else-if="user_pass_login_disabled.data" class="text-center text-gray-600 py-8">{{ __("No login methods are available. Please contact your administrator.") }}</div>
				</div>
			</div>

			<Dialog v-model="forgot.showDialog">
				<template #body-title>
					<h2 class="text-lg font-bold">{{ __("Forgot Password") }}</h2>
				</template>
				<template #body-content>
					<div v-if="forgot.sent" class="text-base text-gray-700">
						{{ __("A link to set a new password has been sent to {0}. Open your email and follow the link.", [forgot.email]) }}
					</div>
					<form v-else class="flex flex-col space-y-4" @submit.prevent="sendResetLink">
						<p class="text-base text-gray-600">
							{{ __("Enter your account email. We will send a link to set a new password.") }}
						</p>
						<Input
							:label="__('Email')"
							:placeholder="__('johndoe@mail.com')"
							v-model="forgot.email"
							type="text"
							autocomplete="username"
						/>
						<ErrorMessage :message="forgot.error" />
						<Button variant="solid" :loading="forgot.loading">
							{{ __("Send Reset Link") }}
						</Button>
					</form>
				</template>
			</Dialog>

			<Dialog v-model="resetPassword.showDialog">
				<template #body-title>
					<h2 class="text-lg font-bold">{{ __("Reset Password") }} </h2>
				</template>
				<template #body-content>
					<p>
						{{ __("Your password has expired. Please reset your password to continue") }}
					</p>
				</template>
				<template #actions>
					<a
						class="inline-flex items-center justify-center gap-2 transition-colors focus:outline-none text-white bg-gray-900 hover:bg-gray-800 active:bg-gray-700 focus-visible:ring focus-visible:ring-gray-400 h-7 text-base px-2 rounded"
						:href="resetPassword.link"
						target="_blank"
					>
						{{ __("Go to Reset Password page") }}
					</a>
				</template>
			</Dialog>

			<Dialog v-model="otp.showDialog">
				<template #body-title>
					<h2 class="text-lg font-bold">{{ __("OTP Verification") }}</h2>
				</template>
				<template #body-content>
					<p class="mb-4" v-if="otp.verification.prompt">
						{{ otp.verification.prompt }}
					</p>

					<form class="flex flex-col space-y-4" @submit.prevent="submit">
						<Input
							:label="__('OTP Code')"
							type="text"
							placeholder="000000"
							v-model="otp.code"
							autocomplete="one-time-code"
						/>
						<ErrorMessage :message="errorMessage" />
						<Button
							:loading="session.otp.loading"
							variant="solid"
							class="disabled:bg-gray-700 disabled:text-white !mt-6"
						>
							{{ __("Verify") }}
						</Button>
					</form>
				</template>
			</Dialog>
		</ion-content>
	</ion-page>
</template>

<script setup>
import { IonPage, IonContent } from "@ionic/vue"
import { inject, reactive, ref } from "vue"
import { Input, Button, ErrorMessage, Dialog, FeatherIcon, call, createResource } from "frappe-ui"


const email = ref(null)
const password = ref(null)
const showPassword = ref(false)

// X-SHA: lupa password -> frappe.core.doctype.user.user.reset_password (sama seperti login ERP)
const forgot = reactive({ showDialog: false, email: "", sent: false, loading: false, error: "" })

function openForgotPassword() {
	forgot.email = (email.value || "").trim()
	forgot.sent = false
	forgot.error = ""
	forgot.showDialog = true
}

async function sendResetLink() {
	const user = (forgot.email || "").trim()
	forgot.error = ""
	if (!user) {
		forgot.error = __("Please enter your email.")
		return
	}
	forgot.loading = true
	try {
		const res = await call("frappe.core.doctype.user.user.reset_password", { user })
		if (res === "disabled") forgot.error = __("This account is disabled. Please contact HR.")
		else if (res === "not allowed") forgot.error = __("Password reset is not allowed for this account.")
		else {
			forgot.email = user
			forgot.sent = true
		}
	} catch (e) {
		const msg = String(e?.messages?.join(" ") || e?.message || "")
		forgot.error = /not found|404/i.test(msg) || e?.exc_type === "DoesNotExistError"
			? __("Email is not registered. Check the spelling or contact HR.")
			: msg || __("Failed to send the reset link. Please try again later.")
	} finally {
		forgot.loading = false
	}
}
const errorMessage = ref("")

const resetPassword = reactive({
	showDialog: false,
	link: "",
})
const otp = reactive({
	showDialog: false,
	tmp_id: "",
	code: "",
	verification: {},
})

const session = inject("$session")
const __ = inject("$translate")

async function submit(e) {
	try {
		let response
		if (otp.showDialog) {
			response = await session.otp(otp.tmp_id, otp.code)
		} else {
			response = await session.login(email.value, password.value)
		}

		if (response.message === "Password Reset") {
			resetPassword.showDialog = true
			resetPassword.link = response.redirect_to
		} else {
			resetPassword.showDialog = false
			resetPassword.link = ""
		}

		// OTP verification
		if (response.verification) {
			if (response.verification.setup) {
				otp.showDialog = true
				otp.tmp_id = response.tmp_id
				otp.verification = response.verification
			} else {
				// Don't bother handling impossible OTP setup (e.g. no phone number).
				window.open("/login?redirect-to=" + encodeURIComponent(window.location.pathname), "_blank")
			}
		}
	} catch (error) {
		errorMessage.value = error.messages.join("\n")
	}
}

const user_pass_login_disabled = createResource({
	url: "hrms.api.system_settings.get_user_pass_login_disabled",
	method: 'GET',
	initialData: 1,
	auto: true,
})

</script>
