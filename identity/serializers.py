from django.contrib.auth import get_user_model
from rest_framework import serializers
from rest_framework.validators import UniqueValidator

from common.phone import normalize_phone
from common.serializers import BaseModelSerializer

from .models import Membership, Organisation, phone_validator

User = get_user_model()


class OrgModelSerializer(BaseModelSerializer):
    """Base for serializers of organisation-owned models. The organisation is set by the view, never by the client."""

    internal_fields = ('organisation',)


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


class OrganisationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Organisation
        fields = ('ref_id', 'name')


class MyMembershipSerializer(serializers.ModelSerializer):
    organisation = OrganisationSerializer(read_only=True)
    roles = serializers.SlugRelatedField(many=True, read_only=True, slug_field='name')

    class Meta:
        model = Membership
        fields = ('ref_id', 'organisation', 'roles')
