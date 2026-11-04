from datetime import date, timedelta

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import ProtectedError, Q
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils.dateparse import parse_date
from django.views.decorators.http import require_POST
from django.views.generic import CreateView, DeleteView, DetailView, ListView, UpdateView

from audit.utils import log
from .forms import ActivityForm, CustomerForm, FollowUpForm, LeadForm, OpportunityForm
from .models import Activity, Customer, FollowUp, Lead, Opportunity
from .scoping import scope

User = get_user_model()


def snapshot(obj):
    return {f.name: str(getattr(obj, f.name)) for f in obj._meta.fields if f.name != 'id'}


def build_crud(M, F, prefix, columns, search=(), filters=(), owner='assigned_to',
               delete_roles=('Admin', 'Manager')):
    entity = M.__name__
    title = M._meta.verbose_name_plural.title()

    class Scoped(LoginRequiredMixin):
        model = M

        def get_queryset(self):
            return scope(self.request.user, M.objects.all(), owner)  # server-side scoping

        def get_context_data(self, **kw):
            ctx = super().get_context_data(**kw)
            ctx.update(title=title, prefix=prefix, singular=M._meta.verbose_name.title())
            return ctx

    class ListV(Scoped, ListView):
        paginate_by = 10
        template_name = 'crm/list.html'

        def get_queryset(self):
            qs = super().get_queryset()
            q = self.request.GET.get('q', '').strip()
            if q and search:
                cond = Q()
                for f in search:
                    cond |= Q(**{f + '__icontains': q})
                qs = qs.filter(cond)
            for param, field, kind in filters:
                v = self.request.GET.get(param, '').strip()
                if not v:
                    continue
                if kind == 'date':
                    d = parse_date(v)
                    if d:
                        qs = qs.filter(**{field: d})
                elif kind == 'users':
                    if v.isdigit():
                        qs = qs.filter(**{field: int(v)})
                else:
                    qs = qs.filter(**{field: v})
            return qs.order_by('-pk')

        def get_context_data(self, **kw):
            ctx = super().get_context_data(**kw)
            u = self.request.user
            sel = []
            for param, field, kind in filters:
                if kind == 'users':
                    if u.is_sales:
                        continue
                    choices = [(x.pk, x.username) for x in User.objects.filter(is_active=True)]
                else:
                    choices = None if kind == 'date' else kind
                sel.append({'param': param, 'label': param.replace('_', ' ').title(),
                            'kind': 'date' if kind == 'date' else 'select',
                            'choices': choices, 'value': self.request.GET.get(param, '')})
            g = self.request.GET.copy()
            g.pop('page', None)
            ctx.update(filters=sel, headers=[c[0] for c in columns], qs=g.urlencode(),
                       rows=[(o, [getattr(o, c[1]) for c in columns]) for o in ctx['object_list']])
            return ctx

    class FormBase(Scoped):
        form_class = F
        template_name = 'crm/form.html'

        def get_form_kwargs(self):
            kw = super().get_form_kwargs()
            kw['user'] = self.request.user
            return kw

    class CreateV(FormBase, CreateView):
        def form_valid(self, form):
            obj = form.save(commit=False)
            if hasattr(obj, 'created_by'):
                obj.created_by = self.request.user
            obj.save()
            log(self.request, 'Create', entity, obj.pk, new=snapshot(obj))
            messages.success(self.request, f'{entity} created successfully.')
            return redirect(f'{prefix}_detail', pk=obj.pk)

    class UpdateV(FormBase, UpdateView):
        def get_object(self, queryset=None):
            obj = super().get_object(queryset)
            self._old = snapshot(obj)   # taken before the form modifies the instance
            return obj

        def form_valid(self, form):
            obj = form.save()
            log(self.request, 'Update', entity, obj.pk, old=self._old, new=snapshot(obj))
            messages.success(self.request, f'{entity} updated successfully.')
            return redirect(f'{prefix}_detail', pk=obj.pk)

    class DetailV(Scoped, DetailView):
        template_name = 'crm/detail.html'

        def get_context_data(self, **kw):
            ctx = super().get_context_data(**kw)
            obj, u = self.object, self.request.user
            ctx['fields'] = [(f.verbose_name.title(), getattr(obj, f.name))
                             for f in M._meta.fields if f.name != 'id']
            hist = []
            if M in (Customer, Lead, Opportunity):
                hist.append(('Follow-ups', scope(u, obj.followups.all())))
            if M is Customer:
                hist.append(('Opportunities', scope(u, obj.opportunities.all())))
            if M in (Customer, Lead):
                hist.append(('Activities', scope(u, obj.activities.all())))
            ctx['history'] = hist
            return ctx

    class DeleteV(Scoped, DeleteView):
        template_name = 'crm/confirm_delete.html'

        def dispatch(self, request, *a, **kw):
            if request.user.is_authenticated and request.user.role not in delete_roles:
                raise PermissionDenied
            return super().dispatch(request, *a, **kw)

        def post(self, request, *a, **kw):
            obj = self.get_object()
            snap, pk = snapshot(obj), obj.pk
            try:
                obj.delete()
            except ProtectedError:
                messages.error(request, 'Cannot delete: other records depend on this one.')
                return redirect(f'{prefix}_detail', pk=pk)
            log(request, 'Delete', entity, pk, old=snap)
            messages.success(request, f'{entity} deleted.')
            return redirect(f'{prefix}_list')

    return dict(list=ListV, create=CreateV, detail=DetailV, update=UpdateV, delete=DeleteV)


MODULES = {
    'customer': build_crud(
        Customer, CustomerForm, 'customer',
        columns=[('Code', 'customer_code'), ('Name', 'customer_name'), ('Email', 'email'),
                 ('Phone', 'phone'), ('Company', 'company_name'), ('Status', 'status'),
                 ('Owner', 'owner')],
        search=['customer_name', 'email', 'phone', 'company_name'],
        filters=[('status', 'status', Customer.STATUS), ('owner', 'owner', 'users')],
        owner='owner'),
    'lead': build_crud(
        Lead, LeadForm, 'lead',
        columns=[('Code', 'lead_code'), ('Name', 'lead_name'), ('Company', 'company_name'),
                 ('Status', 'status'), ('Priority', 'priority'), ('Value', 'expected_value'),
                 ('Assigned To', 'assigned_to')],
        search=['lead_name', 'company_name', 'email'],
        filters=[('status', 'status', Lead.STATUS), ('assigned_to', 'assigned_to', 'users')]),
    'opportunity': build_crud(
        Opportunity, OpportunityForm, 'opportunity',
        columns=[('Name', 'opportunity_name'), ('Customer', 'customer'), ('Stage', 'stage'),
                 ('Amount', 'amount'), ('Prob %', 'probability'),
                 ('Close Date', 'expected_close_date'), ('Assigned To', 'assigned_to')],
        search=['opportunity_name', 'customer__customer_name'],
        filters=[('stage', 'stage', Opportunity.STAGES),
                 ('status', 'status', [('Open', 'Open'), ('Won', 'Won'), ('Lost', 'Lost')]),
                 ('assigned_to', 'assigned_to', 'users')]),
    'followup': build_crud(
        FollowUp, FollowUpForm, 'followup',
        columns=[('Date', 'follow_up_date'), ('Subject', 'subject'), ('Type', 'follow_up_type'),
                 ('Status', 'status'), ('Customer', 'customer'), ('Lead', 'lead'),
                 ('Assigned To', 'assigned_to')],
        search=['subject', 'customer__customer_name', 'lead__lead_name'],
        filters=[('status', 'status', FollowUp.STATUS), ('date', 'follow_up_date', 'date'),
                 ('assigned_to', 'assigned_to', 'users')]),
    'activity': build_crud(
        Activity, ActivityForm, 'activity',
        columns=[('Type', 'activity_type'), ('Subject', 'subject'), ('Date', 'activity_date'),
                 ('Status', 'status'), ('Customer', 'customer'), ('Lead', 'lead'),
                 ('Assigned To', 'assigned_to')],
        search=['subject', 'customer__customer_name', 'lead__lead_name'],
        filters=[('activity_type', 'activity_type', Activity.TYPES),
                 ('activity_date', 'activity_date', 'date'),
                 ('status', 'status', Activity.STATUS),
                 ('assigned_to', 'assigned_to', 'users')]),
}


# ---------- Workflows ----------
@login_required
@require_POST
def lead_convert(request, pk):
    lead = get_object_or_404(scope(request.user, Lead.objects.all()), pk=pk)
    if lead.status != 'Qualified':
        messages.error(request, 'Only Qualified leads can be converted.')
        return redirect('lead_detail', pk=pk)
    if not lead.expected_value or lead.expected_value <= 0:
        messages.error(request, 'Set a positive Expected Value on the lead before converting.')
        return redirect('lead_detail', pk=pk)
    with transaction.atomic():
        customer = Customer.objects.filter(
            Q(email__iexact=lead.email) | Q(phone=lead.phone) |
            Q(customer_name__iexact=lead.lead_name, company_name__iexact=lead.company_name)).first()
        if not customer:
            customer = Customer.objects.create(
                customer_name=lead.lead_name, email=lead.email, phone=lead.phone,
                company_name=lead.company_name, owner=lead.assigned_to, created_by=request.user)
            log(request, 'Create', 'Customer', customer.pk, new=snapshot(customer))
        opp = Opportunity.objects.create(
            opportunity_name=f'{lead.lead_name} - Opportunity', customer=customer, lead=lead,
            amount=lead.expected_value, stage='Qualification', probability=20,
            expected_close_date=date.today() + timedelta(days=30), source=lead.source,
            assigned_to=lead.assigned_to, created_by=request.user)
        old = lead.status
        lead.status = 'Converted'
        lead.save()
        log(request, 'Convert', 'Lead', lead.pk, old=old, new=f'Converted -> Customer {customer.pk}, Opportunity {opp.pk}')
    messages.success(request, 'Lead converted to customer and opportunity.')
    return redirect('opportunity_detail', pk=opp.pk)


def _followup(request, pk):
    return get_object_or_404(scope(request.user, FollowUp.objects.all()), pk=pk)


@login_required
@require_POST
def followup_complete(request, pk):
    f = _followup(request, pk)
    if f.status != 'Planned':
        messages.error(request, 'Only planned follow-ups can be completed.')
    else:
        f.status = 'Completed'
        f.save()
        log(request, 'Complete', 'FollowUp', f.pk, old='Planned', new='Completed')
        messages.success(request, 'Follow-up marked as completed.')
    return redirect('followup_detail', pk=pk)


@login_required
@require_POST
def followup_reschedule(request, pk):
    f = _followup(request, pk)
    new = parse_date(request.POST.get('follow_up_date', ''))
    if f.status != 'Planned':
        messages.error(request, 'Only planned follow-ups can be rescheduled.')
    elif not new:
        messages.error(request, 'Enter a valid date.')
    elif new < date.today():
        messages.error(request, 'Follow-up date cannot be earlier than today.')
    else:
        old = f.follow_up_date
        f.follow_up_date = new
        f.save()
        log(request, 'Reschedule', 'FollowUp', f.pk, old=old, new=new)
        messages.success(request, 'Follow-up rescheduled.')
    return redirect('followup_detail', pk=pk)