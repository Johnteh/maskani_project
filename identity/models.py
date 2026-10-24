from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.core.validators import RegexValidator
from django.db import models
from django.utils import timezone

from common.models import BaseModel
from common.phone import normalize_phone


class UserManager(BaseUserManager):
    def get_by_natural_key(self, phone):
        """Find a user by phone number. authenticate() calls this, so the admin and the API login share it."""
        phone = normalize_phone(phone)
        if not phone:
            raise self.model.DoesNotExist
        return self.get(phone=phone)

    def create_user(self, phone, password=None, email=None, **extra_fields):
        phone = normalize_phone(phone)
        if not phone:
            raise ValueError('A phone number is required')
        user = self.model(
            phone=phone,
            email=self.normalize_email(email) if email else None,
            **extra_fields,
        )
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, phone, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        return self.create_user(phone, password, **extra_fields)


phone_validator = RegexValidator(
    regex=r'^\+[1-9]\d{7,14}$',
    message='Enter the phone number in international format, e.g. +254712345678.',
)


class User(AbstractBaseUser, PermissionsMixin, BaseModel):
    phone = models.CharField(max_length=16, unique=True, validators=[phone_validator])
    phone_verified = models.BooleanField(default=False)
    email = models.EmailField(unique=True, null=True, blank=True)
    first_name = models.CharField(max_length=150, blank=True)
    last_name = models.CharField(max_length=150, blank=True)
    is_staff = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    date_joined = models.DateTimeField(default=timezone.now)

    USERNAME_FIELD = 'phone'
    REQUIRED_FIELDS = []

    objects = UserManager()

    def __str__(self):
        return self.phone

    def get_full_name(self):
        return f'{self.first_name} {self.last_name}'.strip()

    def get_short_name(self):
        return self.first_name

    def clean(self):
        super().clean()
        self.email = self.email or None

    def save(self, *args, **kwargs):
        # "no email" is stored as NULL, never '', so the unique constraint allows many users without one
        self.email = self.email or None
        self.phone = normalize_phone(self.phone)
        is_new = self.pk is None
        super().save(*args, **kwargs)
        if is_new:
            Profile.objects.create(user=self)


class Profile(BaseModel):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    id_number = models.CharField(max_length=30, blank=True)
    date_of_birth = models.DateField(null=True, blank=True)
    address = models.TextField(blank=True)
    sms_opt_in = models.BooleanField(default=True)

    def __str__(self):
        return f'Profile of {self.user}'


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
