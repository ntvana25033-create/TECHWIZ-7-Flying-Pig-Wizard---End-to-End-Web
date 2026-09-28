document.addEventListener("DOMContentLoaded", () => {
    const passwordButtons = document.querySelectorAll("[data-toggle-password]");
    passwordButtons.forEach((button) => {
        button.addEventListener("click", () => {
            const input = document.getElementById(button.dataset.togglePassword);
            if (!input) return;
            const shouldShow = input.type === "password";
            input.type = shouldShow ? "text" : "password";
            button.textContent = shouldShow ? "Hide" : "Show";
        });
    });
    const password = document.getElementById("id_password1") || document.getElementById("id_new_password1");
    const bar = document.getElementById("passwordStrengthBar");
    const text = document.getElementById("passwordStrengthText");
    if (!password || !bar || !text) return;
    password.addEventListener("input", () => {
        const value = password.value;
        let score = 0;
        if (value.length >= 8) score++;
        if (/[A-Z]/.test(value) && /[a-z]/.test(value)) score++;
        if (/\d/.test(value)) score++;
        if (/[^A-Za-z0-9]/.test(value)) score++;
        const states = [
            ["0%", "#7b8a82", "Password should contain at least 8 characters."],
            ["25%", "#ff7777", "Weak password"],
            ["50%", "#ffbe67", "Medium-strength password"],
            ["75%", "#79b8ff", "Good password"],
            ["100%", "#53f47f", "Strong password"]
        ];
        const [width, color, label] = states[score];
        bar.style.width = width;
        bar.style.background = color;
        text.textContent = label;
    });
});
