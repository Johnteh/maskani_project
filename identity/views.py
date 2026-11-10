from django.contrib.auth import get_user_model
from rest_framework import generics, permissions
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken

from .models import Membership
from .serializers import MyMembershipSerializer, RegisterSerializer, UserSerializer

User = get_user_model()


class RegisterView(generics.CreateAPIView):
    queryset = User.objects.all()
    permission_classes = (permissions.AllowAny,)
    serializer_class = RegisterSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        refresh = RefreshToken.for_user(user)
        return Response({
            'user': UserSerializer(user).data,
            'access': str(refresh.access_token),
            'refresh': str(refresh),
        })


class MeView(generics.RetrieveAPIView):
    permission_classes = (permissions.IsAuthenticated,)
    serializer_class = UserSerializer

    def get_object(self):
        return self.request.user


class MyMembershipsView(generics.ListAPIView):
    """The organisations the user can act in, so the app can choose what to send as X-Organisation."""

    permission_classes = (permissions.IsAuthenticated,)
    serializer_class = MyMembershipSerializer

    def get_queryset(self):
        return (
            Membership.objects
            .filter(user=self.request.user, is_active=True)
            .select_related('organisation')
            .prefetch_related('roles')
            .order_by('organisation__name')
        )
