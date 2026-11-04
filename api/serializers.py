import copy

from django.forms.models import model_to_dict
from rest_framework import serializers

from crm.forms import CustomerForm, LeadForm, OpportunityForm
from crm.models import Customer, Lead, Opportunity

READ_ONLY = ('id', 'customer_code', 'lead_code', 'created_by', 'created_date', 'modified_date')


class FormValidatedSerializer(serializers.ModelSerializer):
    """Output DTO + validation through the same ModelForm the UI uses."""
    form_class = None
    owner_field = 'assigned_to'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for f in self.fields.values():          # the form decides what is truly required
            if not f.read_only:
                f.required = False

    def validate(self, attrs):
        user = self.context['request'].user
        if user.is_sales:                       # sales users cannot assign records to others
            attrs[self.owner_field] = getattr(self.instance, self.owner_field) if self.instance else user
        elif self.owner_field not in attrs and not self.instance:
            attrs[self.owner_field] = user

        data = model_to_dict(self.instance) if self.instance else {}
        if not self.instance:
            for f in self.Meta.model._meta.fields:
                if f.has_default() and f.name not in attrs:
                    data[f.name] = f.get_default()
        for k, v in attrs.items():
            data[k] = v.pk if hasattr(v, 'pk') else v
        data = {k: v for k, v in data.items() if v is not None}

        form = self.form_class(data, instance=copy.copy(self.instance) if self.instance else None, user=user)
        if not form.is_valid():
            raise serializers.ValidationError(
                {('non_field_errors' if k == '__all__' else k): list(v) for k, v in form.errors.items()})
        return attrs


def make(model, form, owner):
    meta = type('Meta', (), {'model': model, 'fields': '__all__', 'read_only_fields': READ_ONLY})
    return type(f'{model.__name__}Serializer', (FormValidatedSerializer,),
                {'Meta': meta, 'form_class': form, 'owner_field': owner})


CustomerSerializer = make(Customer, CustomerForm, 'owner')
LeadSerializer = make(Lead, LeadForm, 'assigned_to')
OpportunitySerializer = make(Opportunity, OpportunityForm, 'assigned_to')