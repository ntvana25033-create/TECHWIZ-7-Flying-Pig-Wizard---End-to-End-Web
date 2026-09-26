from django.urls import path

from . import views

app_name = "finance_assistant"

urlpatterns = [
    path("", views.AssistantHomeView.as_view(), name="home"),
    path("new/", views.NewChatView.as_view(), name="new-chat"),
    path("<int:session_id>/delete/", views.DeleteChatView.as_view(), name="delete-chat"),
    path("api/chat/", views.ChatAPIView.as_view(), name="api-chat"),
    path("api/bootstrap/", views.WidgetBootstrapAPIView.as_view(), name="api-bootstrap"),
    path("api/messages/<int:message_id>/rating/", views.MessageRatingAPIView.as_view(), name="api-rating"),
]
