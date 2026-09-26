document.addEventListener("DOMContentLoaded", () => {
  const input = document.querySelector("[data-avatar-input]")
  const preview = document.getElementById("avatarPreview")
  const fallback = document.getElementById("avatarFallback")
  const fileName = document.getElementById("selectedAvatarName")
  const removeAvatar = document.querySelector("input[name='remove_avatar']")

  if (!input || !preview || !fallback) return

  const allowedTypes = new Set([
    "image/jpeg",
    "image/png",
    "image/webp",
    "image/gif"
  ])
  const maxBytes = 5 * 1024 * 1024
  let previewUrl = null

  const releasePreviewUrl = () => {
    if (previewUrl) {
      URL.revokeObjectURL(previewUrl)
      previewUrl = null
    }
  }

  const showFallback = () => {
    releasePreviewUrl()
    preview.hidden = true
    preview.removeAttribute("src")
    fallback.hidden = false
  }

  const restoreExistingPreview = () => {
    const original = preview.dataset.originalSrc || ""
    releasePreviewUrl()
    if (original) {
      preview.src = original
      preview.hidden = false
      fallback.hidden = true
    } else {
      showFallback()
    }
  }

  if (!preview.hidden && preview.getAttribute("src")) {
    preview.dataset.originalSrc = preview.getAttribute("src")
  }

  preview.addEventListener("error", showFallback)

  input.addEventListener("change", () => {
    const file = input.files && input.files[0]
    if (!file) return

    if (!allowedTypes.has(file.type)) {
      input.value = ""
      restoreExistingPreview()
      if (fileName) fileName.textContent = "Please choose a JPG, PNG, WEBP, or GIF image"
      return
    }

    if (file.size > maxBytes) {
      input.value = ""
      restoreExistingPreview()
      if (fileName) fileName.textContent = "Image is too large. Maximum size is 5 MB"
      return
    }

    releasePreviewUrl()
    previewUrl = URL.createObjectURL(file)
    preview.src = previewUrl
    preview.hidden = false
    fallback.hidden = true
    if (fileName) fileName.textContent = file.name
    if (removeAvatar) removeAvatar.checked = false
  })

  if (removeAvatar) {
    removeAvatar.addEventListener("change", () => {
      if (removeAvatar.checked) {
        input.value = ""
        showFallback()
        if (fileName) fileName.textContent = "Profile picture will be removed after saving"
      } else {
        restoreExistingPreview()
        if (fileName) fileName.textContent = preview.dataset.originalSrc ? "Current profile picture" : "No image selected"
      }
    })
  }

  window.addEventListener("beforeunload", releasePreviewUrl)
})
