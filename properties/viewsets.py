from identity.viewsets import OrgModelViewSet

from .models import Property
from .serializers import PropertySerializer


class PropertyViewSet(OrgModelViewSet):
    queryset = Property.objects.all()
    serializer_class = PropertySerializer
    required_permissions = {
        'list': 'property.read',
        'retrieve': 'property.read',
        'create': 'property.create',
        'update': 'property.update',
        'partial_update': 'property.update',
        'destroy': 'property.delete',
    }
