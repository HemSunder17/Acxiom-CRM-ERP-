from .models import AuditLog


def get_ip(request):
    if not request:
        return None
    xff = request.META.get('HTTP_X_FORWARDED_FOR')
    return xff.split(',')[0].strip() if xff else request.META.get('REMOTE_ADDR')


def log(request, action, entity='', record_id='', old='', new='',
        result='Success', user=None, username=''):
    u = user
    if u is None and request is not None and request.user.is_authenticated:
        u = request.user
    AuditLog.objects.create(
        user=u,
        username=username or (u.username if u else ''),
        action=action, entity_name=entity, record_id=str(record_id),
        old_value=str(old), new_value=str(new),
        result=result, ip_address=get_ip(request),
    )