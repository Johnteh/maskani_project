from common.viewsets import BaseModelViewSet

from .permissions import HasPermissions, get_membership


class OrgModelViewSet(BaseModelViewSet):
    """
    A ModelViewSet for data owned by the organisation named in the X-Organisation header.
    Subclasses set `permission_resource` (e.g. 'property'); a custom @action sets `permission_code`.
    See get_permission_code.
    """

    permission_classes = (HasPermissions,)
    permission_resource = None
    permission_code = None

    @property
    def membership(self):
        return get_membership(self.request)

    def get_queryset(self):
        queryset = super().get_queryset()
        if self.membership is None:
            return queryset.none()
        return queryset.filter(organisation=self.membership.organisation)

    def perform_create(self, serializer):
        serializer.save(organisation=self.membership.organisation)
