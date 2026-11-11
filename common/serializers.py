from rest_framework import serializers


class InternalFieldsMixin:
    """
    Removes the fields named in `internal_fields` from the serializer, so they are never shown
    in a response and never accepted from a client. Works with `fields = '__all__'`.
    """

    internal_fields = ()

    def get_fields(self):
        fields = super().get_fields()
        for name in self.internal_fields:
            fields.pop(name, None)
        return fields


class BaseModelSerializer(InternalFieldsMixin, serializers.ModelSerializer):
    """The base every model serializer in the project builds on."""
