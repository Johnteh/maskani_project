from django.contrib.auth import get_user_model
from rest_framework import serializers
from rest_framework.validators import UniqueValidator

from common.phone import normalize_phone

from .models import phone_validator

User = get_user_model()


class PhoneField(serializers.CharField):
    """Accepts 0712345678 or +254712345678 and returns +254712345678."""

    def to_internal_value(self, data):
        return normalize_phone(super().to_internal_value(data))


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8)
    phone = PhoneField(validators=[phone_validator, UniqueValidator(queryset=User.objects.all())])

    class Meta:
        model = User
        fields = ('phone', 'password', 'email', 'first_name', 'last_name')

    def create(self, validated_data):
        return User.objects.create_user(
            phone=validated_data['phone'],
            password=validated_data['password'],
            email=validated_data.get('email'),
            first_name=validated_data.get('first_name', ''),
            last_name=validated_data.get('last_name', ''),
        )


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ('id', 'phone', 'phone_verified', 'email', 'first_name', 'last_name')
        read_only_fields = ('phone_verified',)
