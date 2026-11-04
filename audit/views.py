from django.core.paginator import Paginator
from django.shortcuts import render
from django.utils.dateparse import parse_date

from accounts.permissions import role_required
from .models import AuditLog


@role_required('Admin')
def audit_list(request):
    qs = AuditLog.objects.all()
    g = request.GET
    user = g.get('user', '').strip()
    module = g.get('module', '').strip()
    action = g.get('action', '').strip()
    d_from = parse_date(g.get('date_from', ''))
    d_to = parse_date(g.get('date_to', ''))

    if user:
        qs = qs.filter(username__icontains=user)
    if module:
        qs = qs.filter(entity_name=module)
    if action:
        qs = qs.filter(action=action)
    if d_from:
        qs = qs.filter(created_date__date__gte=d_from)
    if d_to:
        qs = qs.filter(created_date__date__lte=d_to)

    params = g.copy()
    params.pop('page', None)
    page = Paginator(qs, 20).get_page(g.get('page'))
    return render(request, 'audit/list.html', {
        'page_obj': page,
        'modules': AuditLog.objects.exclude(entity_name='').values_list('entity_name', flat=True).distinct().order_by('entity_name'),
        'actions': AuditLog.objects.values_list('action', flat=True).distinct().order_by('action'),
        'f': {'user': user, 'module': module, 'action': action,
              'date_from': g.get('date_from', ''), 'date_to': g.get('date_to', '')},
        'qs': params.urlencode(),
    })