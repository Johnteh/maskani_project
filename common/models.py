import uuid

from django.db import models


class BaseModel(models.Model):
    ref_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True

    def __str__(self):
        return getattr(self, 'name', None) or f'{type(self).__name__} {self.pk}'
