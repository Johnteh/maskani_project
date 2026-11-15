from identity.serializers import OrgModelSerializer

from .models import Property


class PropertySerializer(OrgModelSerializer):
    class Meta:
        model = Property
        fields = '__all__'
