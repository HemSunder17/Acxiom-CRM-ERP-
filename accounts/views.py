import json
from django.db.models import Count, Sum
from django.db.models.functions import TruncMonth
from audit.models import AuditLog
from crm.models import Customer, FollowUp, Lead, Opportunity
from crm.scoping import scope
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.shortcuts import redirect, render
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from datetime import timedelta

from audit.utils import log
from .forms import LoginForm, RegisterForm
from .models import User


def login_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    form = LoginForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        ident = form.cleaned_data['identifier'].strip()
        pwd = form.cleaned_data['password']
        user = User.objects.filter(Q(username__iexact=ident) | Q(email__iexact=ident)).first()

        if user and user.is_locked_out:
            log(request, 'Failed Login', 'User', user.pk, new='Account locked',
                result='Failure', user=user)
            messages.error(request, 'Account is temporarily locked. Please try again later.')
        elif user and user.is_active and user.check_password(pwd):
            user.failed_login_count = 0
            user.lockout_end = None
            user.save(update_fields=['failed_login_count', 'lockout_end'])
            login(request, user)
            log(request, 'Login', 'User', user.pk, user=user)
            nxt = request.GET.get('next', '')
            if nxt and url_has_allowed_host_and_scheme(nxt, allowed_hosts={request.get_host()}):
                return redirect(nxt)
            return redirect('dashboard')
        else:
            if user:
                user.failed_login_count += 1
                if user.failed_login_count >= settings.MAX_FAILED_ATTEMPTS:
                    user.lockout_end = timezone.now() + timedelta(minutes=settings.LOCKOUT_MINUTES)
                    user.failed_login_count = 0
                    log(request, 'Lockout', 'User', user.pk, result='Failure', user=user)
                user.save(update_fields=['failed_login_count', 'lockout_end'])
            log(request, 'Failed Login', 'User', user.pk if user else '',
                result='Failure', user=user, username=ident)
            messages.error(request, 'Invalid credentials.')
    return render(request, 'accounts/login.html', {'form': form})


def register_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    form = RegisterForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        user = form.save()  # role defaults to SalesExecutive; users cannot choose their role
        log(request, 'Register', 'User', user.pk, user=user)
        messages.success(request, 'Registration successful. Please log in.')
        return redirect('login')
    return render(request, 'accounts/register.html', {'form': form})


def logout_view(request):
    if request.method == 'POST':
        if request.user.is_authenticated:
            log(request, 'Logout', 'User', request.user.pk)
        logout(request)
    return redirect('login')


@login_required
def dashboard(request):
    u = request.user
    today = timezone.localdate()
    customers = scope(u, Customer.objects.all(), 'owner')
    leads = scope(u, Lead.objects.all())
    opps = scope(u, Opportunity.objects.all())
    followups = scope(u, FollowUp.objects.all())

    closed = ['Won', 'Lost']
    open_opps = opps.exclude(stage__in=closed)
    pipeline = open_opps.aggregate(t=Sum('amount'))['t'] or 0
    weighted = sum((o.amount * o.probability / 100 for o in open_opps), 0)
    pending = followups.filter(status='Planned')

    kpis = [
        ('Total Customers', customers.count(), 'bi-people', 'primary'),
        ('Total Leads', leads.count(), 'bi-person-lines-fill', 'info'),
        ('Open Leads', leads.exclude(status__in=['Lost', 'Converted', 'Unqualified']).count(), 'bi-funnel', 'secondary'),
        ('Total Opportunities', opps.count(), 'bi-briefcase', 'dark'),
        ('Open Opportunities', open_opps.count(), 'bi-folder2-open', 'warning'),
        ('Won Opportunities', opps.filter(stage='Won').count(), 'bi-trophy', 'success'),
        ('Lost Opportunities', opps.filter(stage='Lost').count(), 'bi-x-circle', 'danger'),
        ('Pipeline Value', f'₹{pipeline:,.0f}', 'bi-cash-stack', 'success'),
        ('Weighted Pipeline', f'₹{weighted:,.0f}', 'bi-graph-up', 'primary'),
        ('Pending Follow-Ups', pending.count(), 'bi-calendar-check', 'warning'),
        ('Overdue Follow-Ups', pending.filter(follow_up_date__lt=today).count(), 'bi-exclamation-triangle', 'danger'),
    ]

    # Chart 1: lead status
    lead_labels = ['New', 'Contacted', 'Qualified', 'Lost', 'Converted']
    lc = {r['status']: r['c'] for r in leads.values('status').annotate(c=Count('id'))}
    lead_chart = {'labels': lead_labels, 'data': [lc.get(s, 0) for s in lead_labels]}

    # Chart 2: opportunity pipeline by stage
    stages = ['Qualification', 'Proposal', 'Negotiation', 'Won', 'Lost']
    sc = {r['stage']: r['c'] for r in opps.values('stage').annotate(c=Count('id'))}
    sa = {r['stage']: float(r['t'] or 0) for r in opps.values('stage').annotate(t=Sum('amount'))}
    pipe_chart = {'labels': stages, 'counts': [sc.get(s, 0) for s in stages],
                  'amounts': [sa.get(s, 0) for s in stages]}

    # Chart 3: monthly won/lost totals (by expected close month)
    rows = (opps.filter(stage__in=closed).annotate(m=TruncMonth('expected_close_date'))
            .values('m', 'stage').annotate(t=Sum('amount')).order_by('m'))
    months = sorted({r['m'] for r in rows if r['m']})
    lookup = {(r['m'], r['stage']): float(r['t'] or 0) for r in rows}
    monthly = {'labels': [m.strftime('%b %Y') for m in months],
               'won': [lookup.get((m, 'Won'), 0) for m in months],
               'lost': [lookup.get((m, 'Lost'), 0) for m in months]}

    ctx = {
        'kpis': kpis,
        'upcoming': pending.filter(follow_up_date__gte=today).order_by('follow_up_date')[:5],
        'charts': {'lead': lead_chart, 'pipe': pipe_chart, 'monthly': monthly},
    }
    if u.is_admin:
        ctx['admin_stats'] = [
            ('Users', User.objects.count()),
            ('Active Users', User.objects.filter(is_active=True).count()),
            ('Locked Accounts', User.objects.filter(lockout_end__gt=timezone.now()).count()),
            ('Failed Logins Today', AuditLog.objects.filter(action='Failed Login', created_date__date=today).count()),
            ('Audit Events Today', AuditLog.objects.filter(created_date__date=today).count()),
        ]
    return render(request, 'dashboard.html', ctx)