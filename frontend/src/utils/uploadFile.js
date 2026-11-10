export function getCsrfToken() {
	// Coba dari cookie frappe
	const match = document.cookie.match(/(?:^|;\s*)csrf_token=([^;]*)/)
	if (match) return decodeURIComponent(match[1])

	// Coba dari meta tag
	const meta = document.querySelector('meta[name="csrf-token"]')
	if (meta) return meta.getAttribute("content")

	// Coba dari window
	if (window.csrf_token) return window.csrf_token
	if (window.frappe?.csrf_token) return window.frappe.csrf_token

	return ""
}

export async function uploadFileToBucket(blob, filename, doctype, fieldname) {
	const file = new File([blob], filename, { type: "image/jpeg" })
	const formData = new FormData()
	formData.append("file", file)
	formData.append("is_private", 0)
	formData.append("doctype", doctype)
	formData.append("fieldname", fieldname)

	const token = getCsrfToken()
	console.log("CSRF Token used:", token)

	const res = await fetch("/api/method/upload_file", {
		method: "POST",
		headers: {
			"X-Frappe-CSRF-Token": token,
		},
		body: formData,
	})

	const data = await res.json()
	return data
}
