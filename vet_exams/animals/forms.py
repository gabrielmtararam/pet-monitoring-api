"""Accounts app forms."""

from django import forms

from vet_exams.animals.models import Animal


class AnimalsAdminForm(forms.ModelForm):
    """Animal admin form."""

    class Meta:  # NOQA
        model = Animal
        fields = (
            "name",
            "specie",
            "breed",
            "guardian",
        )
