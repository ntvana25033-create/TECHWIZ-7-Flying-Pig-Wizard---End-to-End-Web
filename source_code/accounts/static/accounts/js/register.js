document.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll("[data-toggle-password]").forEach((button) => {
    button.addEventListener("click", () => {
      const input = document.getElementById(button.dataset.togglePassword);
      if (!input) return;
      const show = input.type === "password";
      input.type = show ? "text" : "password";
      button.textContent = show ? "Ẩn" : "Hiện";
    });
  });

  const password = document.querySelector("[data-password='main']");
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
      ["0%", "#b7c3bd", "Mật khẩu nên có ít nhất 8 ký tự."],
      ["25%", "#d92d20", "Mật khẩu yếu"],
      ["50%", "#f79009", "Mật khẩu trung bình"],
      ["75%", "#2e90fa", "Mật khẩu khá"],
      ["100%", "#176b45", "Mật khẩu mạnh"],
    ];
    const [width, color, label] = states[score];
    bar.style.width = width;
    bar.style.background = color;
    text.textContent = label;
  });
});
