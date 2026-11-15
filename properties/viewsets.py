from identity.viewsets import OrgModelViewSet

from .models import Property
from .serializers import PropertySerializer


class PropertyViewSet(OrgModelViewSet):
    queryset = Property.objects.all()
    serializer_class = PropertySerializer
    permission_resource = 'property'
