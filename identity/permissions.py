import uuid

from rest_framework.exceptions import ParseError
from rest_framework.permissions import BasePermission

from .models import Membership

ORGANISATION_HEADER = 'X-Organisation'


def get_membership(request):
    """The requesting user's active membership in the organisation named by X-Organisation, or None."""
    if not hasattr(request, '_membership'):
        raw = request.headers.get(ORGANISATION_HEADER)
        if not raw:
            raise ParseError(f'The {ORGANISATION_HEADER} header is required.')
        try:
            ref_id = uuid.UUID(raw)
        except ValueError:
            raise ParseError(f'The {ORGANISATION_HEADER} header must be an organisation ref_id.')
        request._membership = (
            Membership.objects
            .filter(user=request.user, organisation__ref_id=ref_id, is_active=True)
            .select_related('organisation')
            .first()
        )
    return request._membership


class HasPermissions(BasePermission):
    """
    Allows a request only if the user's membership in the X-Organisation organisation grants the
    permission code the view lists for this action in `required_permissions`.
    An action the view does not list is denied.
    """

    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        action = getattr(view, 'action', None) or request.method.lower()
        code = getattr(view, 'required_permissions', {}).get(action)
        if code is None:
            return False
        membership = get_membership(request)
        return membership is not None and membership.has_permission(code)
