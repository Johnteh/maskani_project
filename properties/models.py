from django.core.validators import MinValueValidator
from django.db import models

from identity.models import OrganisationOwnedModel


class Property(OrganisationOwnedModel):
    name = models.CharField(max_length=150)
    address = models.TextField()
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name_plural = 'properties'
        ordering = ('name',)


class Frequency(models.TextChoices):
    """How often a charge is billed. Billing code branches on these, so the list is fixed in code."""

    MONTHLY = 'MONTHLY', 'Monthly'
    QUARTERLY = 'QUARTERLY', 'Quarterly'
    HALF_YEARLY = 'HALF_YEARLY', 'Half-yearly'
    ANNUALLY = 'ANNUALLY', 'Annually'
    ONE_OFF = 'ONE_OFF', 'One-off'


class PropertyCharge(OrganisationOwnedModel):
    """A recurring bill that applies to a whole property, e.g. service charge or garbage (amounts in KES)."""

    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name='charges')
    charge_type = models.ForeignKey('catalogue.ChargeType', on_delete=models.PROTECT, related_name='property_charges')
    name = models.CharField(max_length=100, blank=True, help_text='Optional label; the charge type name is used if empty.')
    amount = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(0)])
    frequency = models.CharField(max_length=20, choices=Frequency.choices, default=Frequency.MONTHLY)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ('charge_type__name', 'name')
        constraints = [
            models.UniqueConstraint(
                fields=['property', 'charge_type'],
                condition=models.Q(is_active=True),
                name='one_active_charge_per_type_per_property',
            ),
        ]

    def __str__(self):
        return f'{self.name or self.charge_type.name} ({self.property})'
