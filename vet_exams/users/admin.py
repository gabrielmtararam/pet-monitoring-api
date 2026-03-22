from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.utils.html import format_html

from vet_exams.animals.models import Animal
from vet_exams.users.models import BaseUser


class AnimalInline(admin.TabularInline):
    model = Animal
    extra = 1
    fields = ('display_icon', 'type', 'name', 'specie', 'breed', 'icon')
    readonly_fields = ('display_icon',)
    raw_id_fields = ('icon',)

    def display_icon(self, obj):
        if obj.icon and obj.icon.image:
            return format_html(
                '<img src="{}" style="width: 30px; height: 30px; object-fit: contain;" />',
                obj.icon.image.url
            )
        return "-"


@admin.register(BaseUser)
class BaseUserAdmin(UserAdmin):
    inlines = [AnimalInline]
    ordering = ('email',)
    list_display = ('email', 'first_name', 'last_name', 'is_staff', 'is_active')
    search_fields = ('email', 'first_name', 'last_name')

    fieldsets = (
        (None, {'fields': ('email', 'password')}),
        ('Informações Pessoais', {'fields': ('first_name', 'last_name')}),
        ('Permissões', {
            'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions'),
        }),
        ('Datas Importantes', {'fields': ('last_login',)}),
    )

    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('email', 'password', 'first_name', 'last_name', 'is_staff', 'is_active'),
        }),
    )
