from datetime import date
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import models
from .validators import phone_validator

User = settings.AUTH_USER_MODEL


class Customer(models.Model):
    STATUS = [('Active', 'Active'), ('Inactive', 'Inactive')]
    customer_code = models.CharField(max_length=12, unique=True, null=True, editable=False)
    customer_name = models.CharField(max_length=100)
    email = models.EmailField(max_length=150, unique=True,
                              error_messages={'unique': 'A customer with this email already exists.'})
    phone = models.CharField(max_length=10, unique=True, validators=[phone_validator],
                             error_messages={'unique': 'A customer with this phone already exists.'})
    company_name = models.CharField(max_length=120, blank=True)
    address = models.CharField(max_length=250, blank=True)
    city = models.CharField(max_length=60, blank=True)
    state = models.CharField(max_length=60, blank=True)
    status = models.CharField(max_length=10, choices=STATUS, default='Active')
    notes = models.TextField(blank=True, max_length=1000)
    owner = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                              related_name='owned_customers')
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                                   related_name='created_customers')
    created_date = models.DateTimeField(auto_now_add=True)
    modified_date = models.DateTimeField(auto_now=True)

    def clean(self):
        self.email = (self.email or '').strip().lower()
        dup = Customer.objects.filter(customer_name__iexact=self.customer_name,
                                      company_name__iexact=self.company_name).exclude(pk=self.pk)
        if self.customer_name and dup.exists():
            raise ValidationError('This customer already exists (same name and company).')

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if not self.customer_code:
            self.customer_code = f'CUS{self.pk:05d}'
            super().save(update_fields=['customer_code'])

    def __str__(self):
        return f'{self.customer_name} ({self.customer_code})'


class Lead(models.Model):
    STATUS = [(s, s) for s in ['New', 'Contacted', 'Qualified', 'Unqualified', 'Converted', 'Lost']]
    PRIORITY = [(p, p) for p in ['Low', 'Medium', 'High']]
    SOURCE = [(s, s) for s in ['Website', 'Referral', 'Cold Call', 'Email Campaign', 'Event', 'Social Media', 'Other']]
    # allowed workflow transitions
    TRANSITIONS = {
        'New': ['Contacted', 'Unqualified', 'Lost'],
        'Contacted': ['Qualified', 'Unqualified', 'Lost'],
        'Qualified': ['Converted', 'Lost'],
        'Unqualified': ['Lost'],
        'Converted': [],
        'Lost': [],
    }
    lead_code = models.CharField(max_length=12, unique=True, null=True, editable=False)
    lead_name = models.CharField(max_length=100)
    email = models.EmailField(max_length=150)
    phone = models.CharField(max_length=10, validators=[phone_validator])
    company_name = models.CharField(max_length=120, blank=True)
    source = models.CharField(max_length=20, choices=SOURCE, default='Website')
    status = models.CharField(max_length=15, choices=STATUS, default='New')
    priority = models.CharField(max_length=10, choices=PRIORITY, default='Medium')
    expected_value = models.DecimalField(
        max_digits=12, decimal_places=2, default=0,
        validators=[MinValueValidator(0, 'Expected value cannot be negative.'),
                    MaxValueValidator(100000000, 'Expected value is too large.')])
    notes = models.TextField(blank=True, max_length=1000)
    assigned_to = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                                    related_name='leads')
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                                   related_name='created_leads')
    created_date = models.DateTimeField(auto_now_add=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._orig_status = self.status

    def clean(self):
        self.email = (self.email or '').strip().lower()
        if self.pk and self.status != self._orig_status:
            if self.status not in self.TRANSITIONS.get(self._orig_status, []):
                raise ValidationError({'status': f'Invalid status change: {self._orig_status} '
                                                 f'cannot move to {self.status}.'})

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        self._orig_status = self.status
        if not self.lead_code:
            self.lead_code = f'LEA{self.pk:05d}'
            super().save(update_fields=['lead_code'])

    def __str__(self):
        return f'{self.lead_name} ({self.lead_code})'


class Opportunity(models.Model):
    STAGES = [(s, s) for s in ['Qualification', 'Proposal', 'Negotiation', 'Won', 'Lost']]
    opportunity_name = models.CharField(max_length=120)
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name='opportunities')
    lead = models.ForeignKey(Lead, on_delete=models.SET_NULL, null=True, blank=True,
                             related_name='opportunities')
    amount = models.DecimalField(max_digits=14, decimal_places=2,
                                 validators=[MinValueValidator(0, 'Amount cannot be negative.')])
    stage = models.CharField(max_length=15, choices=STAGES, default='Qualification')
    probability = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(0, 'Probability must be between 0 and 100.'),
                    MaxValueValidator(100, 'Probability must be between 0 and 100.')])
    expected_close_date = models.DateField()
    status = models.CharField(max_length=10, default='Open', editable=False)  # derived from stage
    source = models.CharField(max_length=50, blank=True)
    notes = models.TextField(blank=True, max_length=1000)
    assigned_to = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                                    related_name='opportunities')
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                                   related_name='created_opportunities')
    created_date = models.DateTimeField(auto_now_add=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._orig_close = self.expected_close_date

    @property
    def is_active_opp(self):
        return self.stage not in ('Won', 'Lost')

    @property
    def weighted_amount(self):
        return (self.amount or 0) * (self.probability or 0) / 100

    def clean(self):
        errors = {}
        if self.is_active_opp:
            if self.amount is not None and self.amount <= 0:
                errors['amount'] = 'Opportunity Amount must be greater than 0.'
            changed = (not self.pk) or self.expected_close_date != self._orig_close
            if self.expected_close_date and changed and self.expected_close_date < date.today():
                errors['expected_close_date'] = 'Expected Close Date cannot be in the past.'
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.status = {'Won': 'Won', 'Lost': 'Lost'}.get(self.stage, 'Open')
        super().save(*args, **kwargs)
        self._orig_close = self.expected_close_date

    def __str__(self):
        return self.opportunity_name


class FollowUp(models.Model):
    TYPES = [(t, t) for t in ['Call', 'Meeting', 'Email', 'Task']]
    STATUS = [(s, s) for s in ['Planned', 'Completed', 'Missed', 'Cancelled']]
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, null=True, blank=True,
                                 related_name='followups')
    lead = models.ForeignKey(Lead, on_delete=models.CASCADE, null=True, blank=True,
                             related_name='followups')
    opportunity = models.ForeignKey(Opportunity, on_delete=models.CASCADE, null=True, blank=True,
                                    related_name='followups')
    follow_up_date = models.DateField()
    subject = models.CharField(max_length=150)
    follow_up_type = models.CharField(max_length=10, choices=TYPES, default='Call')
    remarks = models.TextField(blank=True, max_length=1000)
    status = models.CharField(max_length=10, choices=STATUS, default='Planned')
    assigned_to = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                                    related_name='followups')
    created_date = models.DateTimeField(auto_now_add=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._orig_date = self.follow_up_date

    @property
    def is_overdue(self):
        return self.status == 'Planned' and self.follow_up_date < date.today()

    def clean(self):
        if not (self.customer_id or self.lead_id or self.opportunity_id):
            raise ValidationError('Link the follow-up to a customer, lead or opportunity.')
        changed = (not self.pk) or self.follow_up_date != self._orig_date
        if self.status == 'Planned' and self.follow_up_date and changed \
                and self.follow_up_date < date.today():
            raise ValidationError({'follow_up_date': 'Follow-up date cannot be earlier than today.'})

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        self._orig_date = self.follow_up_date

    def __str__(self):
        return self.subject


class Activity(models.Model):
    TYPES = [(t, t) for t in ['Call', 'Meeting', 'Email', 'Task']]
    STATUS = [(s, s) for s in ['Pending', 'Completed', 'Cancelled']]
    activity_type = models.CharField(max_length=10, choices=TYPES)
    subject = models.CharField(max_length=150)
    description = models.TextField(blank=True, max_length=1000)
    activity_date = models.DateField()
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, null=True, blank=True,
                                 related_name='activities')
    lead = models.ForeignKey(Lead, on_delete=models.CASCADE, null=True, blank=True,
                             related_name='activities')
    assigned_to = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                                    related_name='activities')
    status = models.CharField(max_length=10, choices=STATUS, default='Pending')

    def __str__(self):
        return f'{self.activity_type}: {self.subject}'