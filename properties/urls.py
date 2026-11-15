from rest_framework.routers import DefaultRouter

from .viewsets import PropertyViewSet

router = DefaultRouter()
router.register('properties', PropertyViewSet, basename='property')

urlpatterns = router.urls
