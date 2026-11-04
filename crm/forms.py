from datetime import date
from django import forms
from django.contrib.auth import get_user_model
from .models import Customer, Lead, Opportunity, FollowUp, Activity
from .scoping import scope

User = get_user_model()


class StyledModelForm(forms.ModelForm):
    assignee_field = None  # name of the user field that Sales Executives can't change

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        for f in self.fields.values():
            f.widget.attrs['class'] = 'form-select' if isinstance(f.widget, forms.Select) else 'form-control'
        name = self.assignee_field
        if name and name in self.fields:
            f = self.fields[name]
            f.queryset = User.objects.filter(is_active=True)
            if user and user.is_sales:
                f.queryset = User.objects.filter(pk=user.pk)
                if not self.instance.pk:
                    self.initial[name] = user.pk
                f.disabled = True   # server ignores any tampered value
            f.required = True
        for fname in self.fields:
            if isinstance(self.fields[fname].widget, forms.Textarea):
                self.fields[fname].widget.attrs['rows'] = 3

    def _min_today(self, name):
        if name in self.fields and not self.instance.pk:
            self.fields[name].widget.attrs['min'] = date.today().isoformat()


class CustomerForm(StyledModelForm):
    assignee_field = 'owner'

    class Meta:
        model = Customer
        fields = ['customer_name', 'email', 'phone', 'company_name', 'address',
                  'city', 'state', 'status', 'owner', 'notes']
        widgets = {
            'phone': forms.TextInput(attrs={'pattern': '[6-9][0-9]{9}', 'maxlength': 10,
                                            'title': 'Enter a valid 10-digit mobile number'}),
            'email': forms.EmailInput(),
        }


class LeadForm(StyledModelForm):
    assignee_field = 'assigned_to'

    class Meta:
        model = Lead
        fields = ['lead_name', 'email', 'phone', 'company_name', 'source', 'status',
                  'priority', 'expected_value', 'assigned_to', 'notes']
        widgets = {
            'phone': forms.TextInput(attrs={'pattern': '[6-9][0-9]{9}', 'maxlength': 10,
                                            'title': 'Enter a valid 10-digit mobile number'}),
            'expected_value': forms.NumberInput(attrs={'min': 0, 'max': 100000000, 'step': '0.01'}),
        }


class OpportunityForm(StyledModelForm):
    assignee_field = 'assigned_to'

    class Meta:
        model = Opportunity
        fields = ['opportunity_name', 'customer', 'lead', 'amount', 'stage', 'probability',
                  'expected_close_date', 'source', 'assigned_to', 'notes']
        widgets = {
            'amount': forms.NumberInput(attrs={'min': 0.01, 'step': '0.01'}),
            'probability': forms.NumberInput(attrs={'min': 0, 'max': 100}),
            'expected_close_date': forms.DateInput(attrs={'type': 'date'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._min_today('expected_close_date')
        if self.user:  # users can only pick records they are allowed to see
            self.fields['customer'].queryset = scope(self.user, Customer.objects.filter(status='Active'), 'owner')
            self.fields['lead'].queryset = scope(self.user, Lead.objects.all())


class FollowUpForm(StyledModelForm):
    assignee_field = 'assigned_to'

    class Meta:
        model = FollowUp
        fields = ['customer', 'lead', 'opportunity', 'follow_up_date', 'subject',
                  'follow_up_type', 'remarks', 'status', 'assigned_to']
        widgets = {'follow_up_date': forms.DateInput(attrs={'type': 'date'})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._min_today('follow_up_date')
        if self.user:
            self.fields['customer'].queryset = scope(self.user, Customer.objects.all(), 'owner')
            self.fields['lead'].queryset = scope(self.user, Lead.objects.all())
            self.fields['opportunity'].queryset = scope(self.user, Opportunity.objects.all())


class ActivityForm(StyledModelForm):
    assignee_field = 'assigned_to'

    class Meta:
        model = Activity
        fields = ['activity_type', 'subject', 'description', 'activity_date',
                  'customer', 'lead', 'assigned_to', 'status']
        widgets = {'activity_date': forms.DateInput(attrs={'type': 'date'})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.user:
            self.fields['customer'].queryset = scope(self.user, Customer.objects.all(), 'owner')
            self.fields['lead'].queryset = scope(self.user, Lead.objects.all())