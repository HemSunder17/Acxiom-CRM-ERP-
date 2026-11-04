from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from audit.utils import log
from .forms import AdminSetPasswordForm, UserCreateForm, UserEditForm
from .models import User
from .permissions import role_required


@role_required('Admin')
def user_list(request):
    g = request.GET
    qs = User.objects.all().order_by('username')
    q, role, status = g.get('q', '').strip(), g.get('role', ''), g.get('status', '')
    if q:
        qs = qs.filter(Q(username__icontains=q) | Q(email__icontains=q) |
                       Q(first_name__icontains=q) | Q(last_name__icontains=q))
    if role:
        qs = qs.filter(role=role)
    if status == 'active':
        qs = qs.filter(is_active=True)
    elif status == 'inactive':
        qs = qs.filter(is_active=False)
    elif status == 'locked':
        qs = qs.filter(lockout_end__gt=timezone.now())
    params = g.copy()
    params.pop('page', None)
    return render(request, 'accounts/user_list.html', {
        'page_obj': Paginator(qs, 10).get_page(g.get('page')),
        'roles': User.Role.choices, 'f': {'q': q, 'role': role, 'status': status},
        'qs': params.urlencode(),
    })


@role_required('Admin')
def user_create(request):
    form = UserCreateForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        u = form.save()
        log(request, 'Create', 'User', u.pk, new={'username': u.username, 'email': u.email, 'role': u.role})
        messages.success(request, 'User created.')
        return redirect('user_list')
    return render(request, 'accounts/user_form.html', {'form': form, 'heading': 'New User'})


@role_required('Admin')
def user_edit(request, pk):
    target = get_object_or_404(User, pk=pk)
    fields = ('first_name', 'last_name', 'email', 'role', 'is_active')
    old = {k: getattr(target, k) for k in fields}      # captured before the form touches the instance
    form = UserEditForm(request.POST or None, instance=target)
    if request.method == 'POST' and form.is_valid():
        c = form.cleaned_data
        if target.pk == request.user.pk and (not c['is_active'] or c['role'] != 'Admin'):
            form.add_error(None, 'You cannot deactivate or demote your own account.')
        else:
            obj = form.save()
            new = {k: getattr(obj, k) for k in fields}
            if old['role'] != new['role']:
                log(request, 'Role Change', 'User', obj.pk, old=old['role'], new=new['role'])
            if old['is_active'] != new['is_active']:
                log(request, 'Status Change', 'User', obj.pk,
                    old='Active' if old['is_active'] else 'Inactive',
                    new='Active' if new['is_active'] else 'Inactive')
            if any(old[k] != new[k] for k in ('first_name', 'last_name', 'email')):
                log(request, 'Update', 'User', obj.pk,
                    old={k: old[k] for k in ('first_name', 'last_name', 'email')},
                    new={k: new[k] for k in ('first_name', 'last_name', 'email')})
            messages.success(request, 'User updated.')
            return redirect('user_list')
    return render(request, 'accounts/user_form.html',
                  {'form': form, 'heading': f'Edit User: {target.username}'})


@role_required('Admin')
@require_POST
def user_unlock(request, pk):
    target = get_object_or_404(User, pk=pk)
    target.lockout_end = None
    target.failed_login_count = 0
    target.save(update_fields=['lockout_end', 'failed_login_count'])
    log(request, 'Unlock', 'User', target.pk, new='Account unlocked')
    messages.success(request, f'{target.username} unlocked.')
    return redirect('user_list')


@role_required('Admin')
def user_reset_password(request, pk):
    target = get_object_or_404(User, pk=pk)
    form = AdminSetPasswordForm(target, request.POST or None)
    if request.method == 'POST' and form.is_valid():
        form.save()
        target.lockout_end = None
        target.failed_login_count = 0
        target.save(update_fields=['lockout_end', 'failed_login_count'])
        log(request, 'Password Reset', 'User', target.pk, new='Password reset by administrator')  # no secrets logged
        messages.success(request, 'Password reset.')
        return redirect('user_list')
    return render(request, 'accounts/user_form.html',
                  {'form': form, 'heading': f'Reset Password: {target.username}'})