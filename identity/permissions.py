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


# What each standard viewset action is called in a permission code, e.g. 'property.read'.
STANDARD_ACTIONS = {
    'list': 'read',
    'retrieve': 'read',
    'create': 'create',
    'update': 'update',
    'partial_update': 'update',
    'destroy': 'delete',
}


def get_permission_code(view, action):
    """
    The permission code `action` needs on `view`, or None if there is none (the request is then denied).
    A standard action gets '<permission_resource>.<read|create|update|delete>'.
    A custom @action has no derived code: it must name its own, @action(..., permission_code='property.retire').
    """
    code = getattr(view, 'permission_code', None)
    if code:
        return code
    resource = getattr(view, 'permission_resource', None)
    verb = STANDARD_ACTIONS.get(action)
    if not resource or verb is None:
        return None
    return f'{resource}.{verb}'


class HasPermissions(BasePermission):
    """
    Allows a request only if the user's membership in the X-Organisation organisation grants the
    permission code derived for this action (see get_permission_code).
    A view with no `permission_resource`, a custom action with no `permission_code`, or a request
    that matches no action, is denied.
    """

    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        action = getattr(view, 'action', None)
        if action is None:
            return False
        code = get_permission_code(view, action)
        if code is None:
            return False
        membership = get_membership(request)
        return membership is not None and membership.has_permission(code)
