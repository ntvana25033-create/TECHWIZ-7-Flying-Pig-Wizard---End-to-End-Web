document.addEventListener("DOMContentLoaded", () => {
  const input = document.querySelector("[data-avatar-input]")
  const preview = document.getElementById("avatarPreview")
  const fallback = document.getElementById("avatarFallback")
  const fileName = document.getElementById("selectedAvatarName")
  const removeAvatar = document.querySelector("input[name='remove_avatar']")

  if (!input || !preview || !fallback) return

  const showFallback = () => {
    preview.hidden = true
    preview.removeAttribute("src")
    fallback.hidden = false
  }

  preview.addEventListener("error", showFallback)

  input.addEventListener("change", () => {
    const file = input.files && input.files[0]
    if (!file) return

    if (!file.type.startsWith("image/")) {
      showFallback()
      if (fileName) fileName.textContent = "The selected file is not an image"
      return
    }

    preview.src = URL.createObjectURL(file)
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
      }
    })
  }
})
