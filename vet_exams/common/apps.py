from django.apps import AppConfig


class CommonConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'vet_exams.common'
    verbose_name = 'common'
    verbose_name_plural = 'common'
