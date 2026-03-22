from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html

from vet_exams.animals.models import Animal, AnimalIcon, Cat, Bird


@admin.register(AnimalIcon)
class AnimalIconAdmin(admin.ModelAdmin):
    list_display = ('id', 'thumbnail', 'image')

    def thumbnail(self, obj):
        if obj.image:
            return format_html(
                '<img src="{}" style="width: 50px; height: 50px; object-fit: contain;" />',
                obj.image.url
            )
        return "-"

class CatInline(admin.StackedInline):
    model = Cat
    can_delete = False
    extra = 0


class BirdInline(admin.StackedInline):
    model = Bird
    can_delete = False
    extra = 0




@admin.register(Animal)
class AnimalAdmin(admin.ModelAdmin):
    list_display = ('name', 'type', 'specie', 'breed', 'guardian')
    readonly_fields = (
        'display_icon',
        'type',
        'name',
        'specie',
        'breed',
        'guardian',
        'icon',
        'specific_admin_link',
    )
    list_filter = ('type',)
    fields = (
        'display_icon',
        'type',
        'name',
        'specie',
        'breed',
        'guardian',
        'icon',
        'specific_admin_link',
    )
    search_fields = ('name', 'specie', 'breed')

    def display_icon(self, obj):
        if obj.icon and obj.icon.image:
            return format_html(
                '<img src="{}" style="width: 40px; height: 40px; object-fit: contain;" />',
                obj.icon.image.url
            )
        return "-"

    display_icon.short_description = 'Ícone'
    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
    def get_inline_instances(self, request, obj=None):
        inline_instances = []

        if not obj:
            return inline_instances

        if obj.type == 'cat':
            inline_instances.append(CatInline(self.model, self.admin_site))
        elif obj.type == 'bird':
            inline_instances.append(BirdInline(self.model, self.admin_site))

        return inline_instances

    def specific_admin_link(self, obj):
        if not obj:
            return "-"

        if obj.type == 'cat':
            url = reverse('admin:animals_cat_change', args=[obj.pk])
            label = 'Abrir Gato'
        elif obj.type == 'bird':
            url = reverse('admin:animals_bird_change', args=[obj.pk])
            label = 'Abrir Pássaro'
        else:
            return "-"

        return format_html('<a href="{}">🔗 {}</a>', url, label)

    specific_admin_link.short_description = 'Admin específico'

@admin.register(Cat)
class CatAdmin(admin.ModelAdmin):
    list_display = ('name', 'fur_color', 'guardian')

@admin.register(Bird)
class BirdAdmin(admin.ModelAdmin):
    list_display = ('name', 'feather_color', 'guardian')