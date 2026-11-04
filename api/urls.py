from django.urls import include, path
from rest_framework.routers import SimpleRouter

from . import views

router = SimpleRouter(trailing_slash=False)   # matches the spec's /api/customers paths exactly
router.register('customers', views.CustomerViewSet, basename='api-customer')
router.register('leads', views.LeadViewSet, basename='api-lead')
router.register('opportunities', views.OpportunityViewSet, basename='api-opportunity')

urlpatterns = [
    path('auth/login', views.LoginAPI.as_view()),
    path('auth/logout', views.LogoutAPI.as_view()),
    path('reports/pipeline', views.pipeline_report),
    path('', include(router.urls)),
]