from django.urls import path
from . import views, admin_views

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('login/', views.login_view, name='login'),
    path('register/', views.register_view, name='register'),
    path('logout/', views.logout_view, name='logout'),
    path('users/', admin_views.user_list, name='user_list'),
    path('users/new/', admin_views.user_create, name='user_create'),
    path('users/<int:pk>/edit/', admin_views.user_edit, name='user_edit'),
    path('users/<int:pk>/unlock/', admin_views.user_unlock, name='user_unlock'),
    path('users/<int:pk>/reset-password/', admin_views.user_reset_password, name='user_reset_password'),
]