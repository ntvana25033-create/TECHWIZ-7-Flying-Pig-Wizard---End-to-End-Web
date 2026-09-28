def notification_status(request):
    if not getattr(request, "user", None) or not request.user.is_authenticated:
        return {"notification_unread_count": 0}

    try:
        count = request.user.notifications.filter(is_read=False).count()
    except Exception:
        count = 0
    return {"notification_unread_count": count}
