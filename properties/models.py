from django.db import models

from identity.models import OrganisationOwnedModel


class Property(OrganisationOwnedModel):
    name = models.CharField(max_length=150)
    address = models.TextField()
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name_plural = 'properties'
        ordering = ('name',)

    def __str__(self):
        return self.name
