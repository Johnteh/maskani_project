from django.db import models

from common.models import BaseModel


class ChargeType(BaseModel):
    """A standard kind of charge, shared by every organisation, e.g. SERVICE_CHARGE or GARBAGE."""

    code = models.CharField(max_length=50, unique=True)
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ('name',)

    def __str__(self):
        return self.code

    def save(self, *args, **kwargs):
        self.code = self.code.strip().upper()
        super().save(*args, **kwargs)
