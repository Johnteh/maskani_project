from rest_framework import viewsets
from rest_framework.permissions import SAFE_METHODS


class ReadWriteSerializerMixin:
    """
    Lets a view use one serializer for reading (GET, HEAD, OPTIONS) and another for writing
    (POST, PUT, PATCH, DELETE). Set `read_serializer_class` and/or `write_serializer_class`;
    whichever is not set falls back to `serializer_class`.
    """

    read_serializer_class = None
    write_serializer_class = None

    def get_serializer_class(self):
        if self.request.method in SAFE_METHODS:
            serializer_class = self.read_serializer_class
        else:
            serializer_class = self.write_serializer_class
        return serializer_class or super().get_serializer_class()


class BaseModelViewSet(ReadWriteSerializerMixin, viewsets.ModelViewSet):
    """The base every viewset in the project builds on."""
