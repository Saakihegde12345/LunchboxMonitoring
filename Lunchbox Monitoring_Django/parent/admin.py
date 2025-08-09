from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.utils.translation import gettext_lazy as _
from .models import ParentUser, Child, LunchboxAssignment, ParentNotification


class ParentUserAdmin(UserAdmin):
    """Admin interface for the ParentUser model."""
    model = ParentUser
    list_display = ('email', 'first_name', 'last_name', 'is_staff', 'is_active')
    list_filter = ('is_staff', 'is_active')
    fieldsets = (
        (None, {'fields': ('email', 'password')}),
        (_('Personal info'), {'fields': ('first_name', 'last_name', 'phone_number', 'address')}),
        (_('Permissions'), {
            'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions'),
        }),
        (_('Important dates'), {'fields': ('last_login', 'date_joined')}),
    )
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('email', 'password1', 'password2', 'is_staff', 'is_active')}
        ),
    )
    search_fields = ('email', 'first_name', 'last_name')
    ordering = ('email',)


class ChildInline(admin.StackedInline):
    """Inline admin for children in the ParentUser admin."""
    model = Child
    extra = 0
    show_change_link = True


class ParentUserWithChildrenAdmin(ParentUserAdmin):
    """ParentUser admin that includes children inline."""
    inlines = [ChildInline]


class LunchboxAssignmentAdmin(admin.ModelAdmin):
    """Admin interface for lunchbox assignments."""
    list_display = ('lunchbox_id', 'child', 'assigned_date', 'is_active')
    list_filter = ('is_active', 'assigned_date')
    search_fields = ('child__name', 'lunchbox_id')
    raw_id_fields = ('child',)


class ParentNotificationAdmin(admin.ModelAdmin):
    """Admin interface for parent notifications."""
    list_display = ('title', 'parent', 'notification_type', 'is_read', 'created_at')
    list_filter = ('notification_type', 'is_read', 'created_at')
    search_fields = ('title', 'message', 'parent__email')
    readonly_fields = ('created_at',)
    date_hierarchy = 'created_at'


# Register models with admin site
admin.site.register(ParentUser, ParentUserWithChildrenAdmin)
admin.site.register(LunchboxAssignment, LunchboxAssignmentAdmin)
admin.site.register(ParentNotification, ParentNotificationAdmin)
