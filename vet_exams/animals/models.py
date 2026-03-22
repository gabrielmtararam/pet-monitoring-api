from django.db import models

from vet_exams.users.models import BaseUser


class AnimalIcon(models.Model):
    image = models.ImageField(upload_to='animals/icons/')

class Animal(models.Model):
    TYPE_CHOICES = (
        ('cat', 'Gato'),
        ('bird', 'Pássaro'),
    )
    type = models.CharField(max_length=100, choices=TYPE_CHOICES, default='cat', blank=True, null=True)
    name = models.CharField(max_length=100)
    specie = models.CharField(max_length=100)
    breed = models.CharField(max_length=100)
    guardian = models.ForeignKey(BaseUser, on_delete=models.CASCADE)
    icon =  models.ForeignKey(AnimalIcon, on_delete=models.SET_NULL, null=True, blank=True)
    def __str__(self):
        return f"{self.name} - {self.guardian.first_name} ({self.guardian.last_name})"
class Cat(Animal):
    FUR_CHOICES = (
        ('white', 'Branco'),
        ('black', 'Preto'),
    )
    fur_color = models.CharField(max_length=100, choices=FUR_CHOICES, null=True, blank=True)

class Bird(Animal):
    FEATHERS_CHOICES = (
        ('white', 'Branco'),
        ('black', 'Preto'),
    )
    feather_color = models.CharField(max_length=100, choices=FEATHERS_CHOICES, null=True, blank=True)