from common.viewsets import BaseModelViewSet

from .permissions import HasPermissions, get_membership


class OrgModelViewSet(BaseModelViewSet):
    """
    A ModelViewSet whose data belongs to one organisation, chosen by the X-Organisation header.
    Subclasses set `queryset`, `serializer_class` and `required_permissions`, e.g.
    {'list': 'property.read', 'create': 'property.create'}; an action not listed is denied.
    """

    permission_classes = (HasPermissions,)
    organisation_field = 'organisation'
    required_permissions = {}

    @property
    def membership(self):
        return get_membership(self.request)

    def get_queryset(self):
        queryset = super().get_queryset()
        if self.membership is None:
            return queryset.none()
        return queryset.filter(**{self.organisation_field: self.membership.organisation})

    def perform_create(self, serializer):
        serializer.save(**{self.organisation_field: self.membership.organisation})
