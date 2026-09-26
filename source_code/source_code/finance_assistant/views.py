from __future__ import annotations

import json

from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views import View

from transactions.mixins import StudentRequiredMixin

from .models import ChatMessage, ChatSession
from .services import assistant_engine

MAX_MESSAGE_LENGTH = 2000


def _read_json(request):
    try:
        return json.loads(request.body.decode("utf-8") or "{}")
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None


def _serialize_message(message: ChatMessage) -> dict:
    return {
        "id": message.pk,
        "role": message.role,
        "content": message.content,
        "intent": message.intent,
        "rating": message.rating,
        "created_at": message.created_at.isoformat(),
    }


def _make_title(text: str) -> str:
    title = " ".join((text or "").strip().split())
    if not title:
        return "New finance chat"
    if len(title) > 72:
        return title[:69].rstrip() + "..."
    return title


class AssistantHomeView(StudentRequiredMixin, View):
    template_name = "finance_assistant/home.html"

    def get(self, request):
        sessions = list(ChatSession.objects.filter(user=request.user)[:30])
        active_session = None
        requested_id = request.GET.get("session")
        if requested_id:
            active_session = ChatSession.objects.filter(user=request.user, pk=requested_id).first()
        if active_session is None and sessions:
            active_session = sessions[0]

        active_messages = []
        if active_session:
            active_messages = list(active_session.messages.all())

        return render(
            request,
            self.template_name,
            {
                "chat_sessions": sessions,
                "active_session": active_session,
                "active_messages": active_messages,
                "assistant_ai_enabled": bool(getattr(getattr(assistant_engine, "llm", None), "enabled", False)),
            },
        )


class NewChatView(StudentRequiredMixin, View):
    def post(self, request):
        session = ChatSession.objects.create(user=request.user)
        return redirect(f"{reverse('finance_assistant:home')}?session={session.pk}")


class DeleteChatView(StudentRequiredMixin, View):
    def post(self, request, session_id):
        session = get_object_or_404(ChatSession, user=request.user, pk=session_id)
        session.delete()
        return redirect("finance_assistant:home")


class ChatAPIView(StudentRequiredMixin, View):
    def post(self, request):
        payload = _read_json(request)
        if payload is None:
            return JsonResponse({"error": "Invalid JSON body."}, status=400)

        text = str(payload.get("message", "")).strip()
        if not text:
            return JsonResponse({"error": "Message cannot be empty."}, status=400)
        if len(text) > MAX_MESSAGE_LENGTH:
            return JsonResponse(
                {"error": f"Message is too long. Maximum length is {MAX_MESSAGE_LENGTH} characters."},
                status=400,
            )

        session_id = payload.get("session_id")
        session = None
        if session_id:
            session = ChatSession.objects.filter(user=request.user, pk=session_id).first()
            if session is None:
                return JsonResponse({"error": "Chat session not found."}, status=404)

        with transaction.atomic():
            if session is None:
                session = ChatSession.objects.create(
                    user=request.user,
                    title=_make_title(text),
                )
            elif session.title == "New finance chat" and not session.messages.exists():
                session.title = _make_title(text)
                session.save(update_fields=["title", "updated_at"])

            history = list(
                session.messages.order_by("-created_at", "-id")[:8].values("role", "content")
            )
            history.reverse()

            user_message = ChatMessage.objects.create(
                session=session,
                role=ChatMessage.Role.USER,
                content=text,
            )

            result = assistant_engine.reply(request.user, text, history=history)
            assistant_message = ChatMessage.objects.create(
                session=session,
                role=ChatMessage.Role.ASSISTANT,
                content=result["answer"],
                intent=result.get("intent", ""),
                metadata={
                    "source": result.get("source", ""),
                    "snapshot": result.get("snapshot", {}),
                },
            )
            session.last_message_at = timezone.now()
            if session.title == "New finance chat":
                session.title = _make_title(text)
            session.save(update_fields=["title", "last_message_at", "updated_at"])

        return JsonResponse(
            {
                "session": {"id": session.pk, "title": session.title},
                "user_message": _serialize_message(user_message),
                "assistant_message": _serialize_message(assistant_message),
                "source": result.get("source", ""),
                "snapshot": result.get("snapshot", {}),
            }
        )


class WidgetBootstrapAPIView(StudentRequiredMixin, View):
    def get(self, request):
        session = ChatSession.objects.filter(user=request.user).first()
        if not session:
            return JsonResponse({"session": None, "messages": []})
        messages = list(session.messages.order_by("-created_at", "-id")[:20])
        messages.reverse()
        return JsonResponse(
            {
                "session": {"id": session.pk, "title": session.title},
                "messages": [_serialize_message(message) for message in messages],
            }
        )


class MessageRatingAPIView(StudentRequiredMixin, View):
    def post(self, request, message_id):
        payload = _read_json(request)
        if payload is None:
            return JsonResponse({"error": "Invalid JSON body."}, status=400)
        try:
            rating = int(payload.get("rating", 0))
        except (TypeError, ValueError):
            rating = 0
        if rating not in {-1, 0, 1}:
            return JsonResponse({"error": "Rating must be -1, 0, or 1."}, status=400)

        message = get_object_or_404(
            ChatMessage,
            pk=message_id,
            role=ChatMessage.Role.ASSISTANT,
            session__user=request.user,
        )
        message.rating = rating
        message.save(update_fields=["rating"])
        return JsonResponse({"ok": True, "rating": rating})
