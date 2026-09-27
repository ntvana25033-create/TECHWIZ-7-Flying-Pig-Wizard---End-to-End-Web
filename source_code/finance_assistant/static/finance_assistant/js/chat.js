(function () {
    "use strict";

    function getCookie(name) {
        const value = `; ${document.cookie}`;
        const parts = value.split(`; ${name}=`);
        if (parts.length === 2) return parts.pop().split(";").shift();
        return "";
    }

    function escapeHtml(value) {
        return String(value || "")
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#039;");
    }

    function formatMessage(value) {
        let safe = escapeHtml(value);
        safe = safe.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
        return safe.replace(/\n/g, "<br>");
    }

    function postJson(url, data) {
        return fetch(url, {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "X-CSRFToken": getCookie("csrftoken"),
                "X-Requested-With": "XMLHttpRequest"
            },
            body: JSON.stringify(data)
        }).then(async (response) => {
            const payload = await response.json().catch(() => ({}));
            if (!response.ok) throw new Error(payload.error || "Request failed.");
            return payload;
        });
    }

    function makeTyping(widgetMode) {
        const article = document.createElement("article");
        article.className = widgetMode ? "cc-ai-message assistant loading" : "assistant-message assistant loading";
        article.dataset.typing = "1";
        if (!widgetMode) {
            const avatar = document.createElement("div");
            avatar.className = "assistant-message-avatar";
            avatar.textContent = "AI";
            article.appendChild(avatar);
            const wrap = document.createElement("div");
            wrap.className = "assistant-message-wrap";
            const bubble = document.createElement("div");
            bubble.className = "assistant-message-bubble";
            bubble.innerHTML = '<span class="cc-ai-typing"><i></i><i></i><i></i></span>';
            wrap.appendChild(bubble);
            article.appendChild(wrap);
        } else {
            const bubble = document.createElement("div");
            bubble.className = "cc-ai-message-bubble";
            bubble.innerHTML = '<span class="cc-ai-typing"><i></i><i></i><i></i></span>';
            article.appendChild(bubble);
        }
        return article;
    }

    function makeMessage(message, widgetMode) {
        const role = message.role === "assistant" ? "assistant" : "user";
        const article = document.createElement("article");
        article.className = widgetMode ? `cc-ai-message ${role}` : `assistant-message ${role}`;
        if (message.id) article.dataset.messageId = message.id;

        if (widgetMode) {
            const bubble = document.createElement("div");
            bubble.className = "cc-ai-message-bubble";
            bubble.innerHTML = formatMessage(message.content);
            article.appendChild(bubble);
            return article;
        }

        const avatar = document.createElement("div");
        avatar.className = "assistant-message-avatar";
        avatar.textContent = role === "assistant" ? "AI" : "YOU";
        article.appendChild(avatar);

        const wrap = document.createElement("div");
        wrap.className = "assistant-message-wrap";
        const bubble = document.createElement("div");
        bubble.className = "assistant-message-bubble";
        bubble.innerHTML = formatMessage(message.content);
        wrap.appendChild(bubble);

        const meta = document.createElement("div");
        meta.className = "assistant-message-meta";
        const time = document.createElement("time");
        const date = message.created_at ? new Date(message.created_at) : new Date();
        time.textContent = Number.isNaN(date.getTime()) ? "now" : date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
        meta.appendChild(time);

        if (role === "assistant" && message.id) {
            const rating = document.createElement("span");
            rating.className = "assistant-rating";
            rating.dataset.ratingControls = "1";
            rating.dataset.messageId = message.id;
            const useful = document.createElement("button");
            useful.type = "button";
            useful.dataset.rating = "1";
            useful.textContent = "Useful";
            const needs = document.createElement("button");
            needs.type = "button";
            needs.dataset.rating = "-1";
            needs.textContent = "Needs work";
            rating.append(useful, needs);
            meta.appendChild(rating);
        }

        wrap.appendChild(meta);
        article.appendChild(wrap);
        return article;
    }

    class FinanceChat {
        constructor(root, options) {
            this.root = root;
            this.widgetMode = !!options.widgetMode;
            this.chatUrl = root.dataset.chatUrl;
            this.bootstrapUrl = root.dataset.bootstrapUrl || "";
            this.ratingBase = root.dataset.ratingBase || "/assistant/api/messages/";
            this.sessionId = root.dataset.sessionId || null;
            this.messages = root.querySelector("[data-chat-messages]");
            this.form = root.querySelector("[data-chat-form]");
            this.textarea = this.form ? this.form.querySelector("textarea") : null;
            this.submit = this.form ? this.form.querySelector('button[type="submit"]') : null;
            this.loaded = !this.widgetMode;
            this.bind();
            this.renderExisting();
        }

        renderExisting() {
            this.root.querySelectorAll("[data-render-message]").forEach((node) => {
                node.innerHTML = formatMessage(node.textContent);
                node.removeAttribute("data-render-message");
            });
            this.scrollBottom();
        }

        bind() {
            if (this.form) {
                this.form.addEventListener("submit", (event) => {
                    event.preventDefault();
                    this.send(this.textarea.value);
                });
            }
            if (this.textarea) {
                this.textarea.addEventListener("keydown", (event) => {
                    if (event.key === "Enter" && !event.shiftKey) {
                        event.preventDefault();
                        this.form.requestSubmit();
                    }
                });
                this.textarea.addEventListener("input", () => this.autoSize());
            }
            this.root.querySelectorAll("[data-prompt]").forEach((button) => {
                button.addEventListener("click", () => this.send(button.dataset.prompt || ""));
            });
            this.root.addEventListener("click", (event) => {
                const button = event.target.closest("[data-rating]");
                if (!button) return;
                const controls = button.closest("[data-rating-controls]");
                if (!controls) return;
                this.rate(controls, Number(button.dataset.rating));
            });
        }

        autoSize() {
            if (!this.textarea) return;
            this.textarea.style.height = "auto";
            this.textarea.style.height = Math.min(this.textarea.scrollHeight, 150) + "px";
        }

        clearEmpty() {
            this.root.querySelectorAll("[data-chat-empty]").forEach((node) => node.remove());
        }

        append(message) {
            this.clearEmpty();
            this.messages.appendChild(makeMessage(message, this.widgetMode));
            this.scrollBottom();
        }

        scrollBottom() {
            if (!this.messages) return;
            requestAnimationFrame(() => { this.messages.scrollTop = this.messages.scrollHeight; });
        }

        setBusy(busy) {
            if (this.submit) this.submit.disabled = busy;
            if (this.textarea) this.textarea.disabled = busy;
        }

        async send(rawText) {
            const text = String(rawText || "").trim();
            if (!text || !this.chatUrl || !this.messages) return;
            if (text.length > 2000) return;

            if (this.textarea) {
                this.textarea.value = "";
                this.autoSize();
            }
            this.append({ role: "user", content: text, created_at: new Date().toISOString() });
            const typing = makeTyping(this.widgetMode);
            this.messages.appendChild(typing);
            this.scrollBottom();
            this.setBusy(true);

            try {
                const payload = await postJson(this.chatUrl, {
                    message: text,
                    session_id: this.sessionId
                });
                this.sessionId = String(payload.session.id);
                this.root.dataset.sessionId = this.sessionId;
                typing.remove();
                this.append(payload.assistant_message);

                if (!this.widgetMode && window.history && payload.session.id) {
                    const url = new URL(window.location.href);
                    if (!url.searchParams.get("session")) {
                        url.searchParams.set("session", payload.session.id);
                        window.history.replaceState({}, "", url);
                    }
                }
            } catch (error) {
                typing.remove();
                this.append({
                    role: "assistant",
                    content: `I couldn't process that request: ${error.message || "unknown error"}`,
                    created_at: new Date().toISOString()
                });
            } finally {
                this.setBusy(false);
                if (this.textarea) this.textarea.focus();
            }
        }

        async bootstrap() {
            if (this.loaded || !this.bootstrapUrl) return;
            this.loaded = true;
            try {
                const response = await fetch(this.bootstrapUrl, {
                    headers: { "X-Requested-With": "XMLHttpRequest" }
                });
                if (!response.ok) return;
                const payload = await response.json();
                if (payload.session) this.sessionId = String(payload.session.id);
                if (payload.messages && payload.messages.length) {
                    this.messages.innerHTML = "";
                    payload.messages.forEach((message) => this.messages.appendChild(makeMessage(message, this.widgetMode)));
                    this.scrollBottom();
                }
            } catch (_) {
                // The widget can still start a new conversation if history loading fails.
            }
        }

        async rate(controls, rating) {
            const messageId = controls.dataset.messageId;
            if (!messageId) return;
            try {
                await postJson(`${this.ratingBase}${messageId}/rating/`, { rating });
                controls.querySelectorAll("[data-rating]").forEach((button) => {
                    button.classList.toggle("selected", Number(button.dataset.rating) === rating);
                });
            } catch (_) {
                // Rating is optional and should never interrupt the chat experience.
            }
        }
    }

    document.addEventListener("DOMContentLoaded", function () {
        document.querySelectorAll("[data-finance-chat-page]").forEach((root) => {
            new FinanceChat(root, { widgetMode: false });
        });

        document.querySelectorAll("[data-finance-widget]").forEach((root) => {
            const chat = new FinanceChat(root, { widgetMode: true });
            const launcher = root.querySelector(".cc-ai-launcher");
            const panel = root.querySelector(".cc-ai-panel");
            const close = root.querySelector(".cc-ai-close");
            if (!launcher || !panel) return;

            function openPanel() {
                panel.hidden = false;
                launcher.setAttribute("aria-expanded", "true");
                chat.bootstrap();
                setTimeout(() => chat.textarea && chat.textarea.focus(), 50);
            }
            function closePanel() {
                panel.hidden = true;
                launcher.setAttribute("aria-expanded", "false");
            }
            launcher.addEventListener("click", () => panel.hidden ? openPanel() : closePanel());
            if (close) close.addEventListener("click", closePanel);
        });
    });
})();
