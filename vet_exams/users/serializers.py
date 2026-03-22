
from rest_framework import serializers

from vet_exams.users.models import BaseUser


class UserRegistrationSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True)

    class Meta:
        model = BaseUser
        fields = ('email', 'password', 'first_name', 'last_name')

    def create(self, validated_data):
        return BaseUser.objects.create_user(**validated_data)

class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)

