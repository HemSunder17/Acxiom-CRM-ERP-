from django.contrib import admin
from .models import Customer, Lead, Opportunity, FollowUp, Activity

for m in (Customer, Lead, Opportunity, FollowUp, Activity):
    admin.site.register(m)