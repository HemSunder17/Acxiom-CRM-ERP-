from django.urls import path
from . import views

SLUGS = {'customer': 'customers', 'lead': 'leads', 'opportunity': 'opportunities',
         'followup': 'followups', 'activity': 'activities'}

urlpatterns = []
for p, v in views.MODULES.items():
    s = SLUGS[p]
    urlpatterns += [
        path(f'{s}/', v['list'].as_view(), name=f'{p}_list'),
        path(f'{s}/new/', v['create'].as_view(), name=f'{p}_create'),
        path(f'{s}/<int:pk>/', v['detail'].as_view(), name=f'{p}_detail'),
        path(f'{s}/<int:pk>/edit/', v['update'].as_view(), name=f'{p}_edit'),
        path(f'{s}/<int:pk>/delete/', v['delete'].as_view(), name=f'{p}_delete'),
    ]

urlpatterns += [
    path('leads/<int:pk>/convert/', views.lead_convert, name='lead_convert'),
    path('followups/<int:pk>/complete/', views.followup_complete, name='followup_complete'),
    path('followups/<int:pk>/reschedule/', views.followup_reschedule, name='followup_reschedule'),
]