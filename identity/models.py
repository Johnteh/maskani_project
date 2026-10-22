from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.core.validators import RegexValidator
from django.db import models

from common.models import BaseModel


class UserManager(BaseUserManager):
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError('Email is required')
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        return self.create_user(email, password, **extra_fields)


phone_validator = RegexValidator(
    regex=r'^\+[1-9]\d{7,14}$',
    message='Enter the phone number in international format, e.g. +254712345678.',
)


class User(AbstractUser, BaseModel):
    username = None
    email = models.EmailField(unique=True)
    phone = models.CharField(
        max_length=16, unique=True, null=True, blank=True, validators=[phone_validator],
    )
    phone_verified = models.BooleanField(default=False)

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = []

    objects = UserManager()

    def save(self, *args, **kwargs):
        # store "no phone" as NULL, never '', so the unique constraint allows many users without one
        self.phone = self.phone or None
        super().save(*args, **kwargs)


class Organisation(BaseModel):
    name = models.CharField(max_length=150)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ('name',)

    def __str__(self):
        return self.name


class Permission(BaseModel):
    code = models.CharField(max_length=100, unique=True)
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)

    class Meta:
        ordering = ('code',)

    def __str__(self):
        return self.code


class Role(BaseModel):
    name = models.CharField(max_length=100, unique=True)
    permissions = models.ManyToManyField(Permission, blank=True, related_name='roles')

    class Meta:
        ordering = ('name',)

    def __str__(self):
        return self.name


class Membership(BaseModel):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='memberships')
    organisation = models.ForeignKey(Organisation, on_delete=models.CASCADE, related_name='memberships')
    roles = models.ManyToManyField(Role, blank=True, related_name='memberships')
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['user', 'organisation'], name='one_membership_per_organisation'),
        ]

    def __str__(self):
        return f'{self.user} @ {self.organisation}'
