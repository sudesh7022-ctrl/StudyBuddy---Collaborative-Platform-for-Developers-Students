from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.translation import gettext_lazy as _
from .models import Room, Topic, Message

User = get_user_model()


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    """Admin for the project's user model with useful list/search fields."""
    ordering = ("-id",)
    list_display = ("id", "username", "email", "is_active", "is_staff", "is_superuser")
    list_display_links = ("username", "email")
    search_fields = ("username", "email")
    list_filter = ("is_staff", "is_superuser", "is_active", "date_joined")
    readonly_fields = ("last_login", "date_joined")

    fieldsets = (
        (None, {"fields": ("username", "email", "password")}),
        (_("Personal info"), {"fields": ("first_name", "last_name")}),
        (_("Permissions"), {
            "fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions"),
        }),
        (_("Important dates"), {"fields": ("last_login", "date_joined")}),
    )

    add_fieldsets = (
        (None, {
            "classes": ("wide",),
            "fields": ("username", "email", "password1", "password2", "is_staff", "is_superuser"),
        }),
    )

    def get_queryset(self, request):
        # Use default queryset but you can customize if you want to hide superusers etc.
        return super().get_queryset(request)


# Register other models with small customizations for admin UX
@admin.register(Room)
class RoomAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "host", "topic", "updated", "created")
    list_display_links = ("name",)
    search_fields = ("name", "host__username", "topic__name")
    list_filter = ("topic",)
    ordering = ("-updated", "-created")


@admin.register(Topic)
class TopicAdmin(admin.ModelAdmin):
    list_display = ("id", "name")
    search_fields = ("name",)
    ordering = ("name",)


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "room", "short_body", "is_toxic", "is_visible", "created", "updated")
    list_display_links = ("short_body",)
    search_fields = ("user__username", "body", "room__name")
    list_filter = ("is_toxic", "is_visible", "created")
    ordering = ("-created",)

    def short_body(self, obj):
        return (obj.body[:120] + "...") if len(obj.body or "") > 120 else (obj.body or "")
    short_body.short_description = "Message"
