from django.contrib.auth import get_user_model, login, logout
from django.core.exceptions import ValidationError as DjangoValidationError
from django.conf import settings
from django.db.models import Q
from django.db.models.deletion import ProtectedError
from django.utils import timezone
from datetime import timedelta
from rest_framework import status, viewsets
from rest_framework.decorators import api_view
from rest_framework.permissions import AllowAny, BasePermission, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from audit.utils import log
from crm.models import Customer, Lead, Opportunity
from crm.scoping import scope
from crm.views import snapshot
from . import serializers as S

User = get_user_model()


class DeleteRoles(BasePermission):
    def has_permission(self, request, view):
        if request.method == 'DELETE':
            return request.user.role in ('Admin', 'Manager')
        return True


class ScopedViewSet(viewsets.ModelViewSet):
    model = None
    owner = 'assigned_to'
    search_fields = ()
    filter_fields = ()
    permission_classes = [IsAuthenticated, DeleteRoles]
    http_method_names = ['get', 'post', 'put', 'delete', 'head', 'options']

    def get_queryset(self):
        qs = scope(self.request.user, self.model.objects.all(), self.owner)  # server-side scoping
        p = self.request.query_params
        q = p.get('q', '').strip()
        if q and self.search_fields:
            cond = Q()
            for f in self.search_fields:
                cond |= Q(**{f + '__icontains': q})
            qs = qs.filter(cond)
        for f in self.filter_fields:
            v = p.get(f, '').strip()
            if v:
                try:
                    qs = qs.filter(**{f: v})
                except (ValueError, DjangoValidationError):
                    return qs.none()
        return qs.order_by('-pk')

    def perform_create(self, serializer):
        kw = {}
        if any(f.name == 'created_by' for f in self.model._meta.fields):
            kw['created_by'] = self.request.user
        obj = serializer.save(**kw)
        log(self.request, 'Create', self.model.__name__, obj.pk, new=snapshot(obj))

    def update(self, request, *args, **kwargs):
        self._old = snapshot(self.get_object())
        return super().update(request, *args, **kwargs)

    def perform_update(self, serializer):
        obj = serializer.save()
        log(self.request, 'Update', self.model.__name__, obj.pk, old=self._old, new=snapshot(obj))

    def destroy(self, request, *args, **kwargs):
        obj = self.get_object()
        snap, pk = snapshot(obj), obj.pk
        try:
            obj.delete()
        except ProtectedError:
            return Response({'detail': 'Cannot delete: other records depend on this one.'},
                            status=status.HTTP_409_CONFLICT)
        log(request, 'Delete', self.model.__name__, pk, old=snap)
        return Response(status=status.HTTP_204_NO_CONTENT)


class CustomerViewSet(ScopedViewSet):
    model, owner = Customer, 'owner'
    serializer_class = S.CustomerSerializer
    search_fields = ('customer_name', 'email', 'phone', 'company_name')
    filter_fields = ('status',)


class LeadViewSet(ScopedViewSet):
    model = Lead
    serializer_class = S.LeadSerializer
    search_fields = ('lead_name', 'company_name', 'email')
    filter_fields = ('status', 'assigned_to')


class OpportunityViewSet(ScopedViewSet):
    model = Opportunity
    serializer_class = S.OpportunitySerializer
    search_fields = ('opportunity_name', 'customer__customer_name')
    filter_fields = ('stage', 'status', 'assigned_to')


class LoginAPI(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'login'

    def post(self, request):
        req = request._request
        ident = str(request.data.get('username', '')).strip()
        pwd = str(request.data.get('password', ''))
        if not ident or not pwd:
            return Response({'detail': 'Username and password are required.'}, status=400)
        user = User.objects.filter(Q(username__iexact=ident) | Q(email__iexact=ident)).first()
        if user and user.is_locked_out:
            log(req, 'Failed Login', 'User', user.pk, new='Account locked', result='Failure', user=user)
            return Response({'detail': 'Account is temporarily locked.'}, status=403)
        if user and user.is_active and user.check_password(pwd):
            user.failed_login_count = 0
            user.lockout_end = None
            user.save(update_fields=['failed_login_count', 'lockout_end'])
            login(req, user)
            log(req, 'Login', 'User', user.pk, user=user)
            return Response({'username': user.username, 'role': user.role})
        if user:
            user.failed_login_count += 1
            if user.failed_login_count >= settings.MAX_FAILED_ATTEMPTS:
                user.lockout_end = timezone.now() + timedelta(minutes=settings.LOCKOUT_MINUTES)
                user.failed_login_count = 0
                log(req, 'Lockout', 'User', user.pk, result='Failure', user=user)
            user.save(update_fields=['failed_login_count', 'lockout_end'])
        log(req, 'Failed Login', 'User', user.pk if user else '', result='Failure', user=user, username=ident)
        return Response({'detail': 'Invalid credentials.'}, status=401)


class LogoutAPI(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        log(request._request, 'Logout', 'User', request.user.pk)
        logout(request._request)
        return Response({'detail': 'Logged out.'})


@api_view(['GET'])
def pipeline_report(request):
    opps = list(scope(request.user, Opportunity.objects.all()).select_related('assigned_to'))

    def group(keyfn):
        out = {}
        for o in opps:
            d = out.setdefault(keyfn(o), {'count': 0, 'amount': 0.0, 'weighted': 0.0})
            d['count'] += 1
            d['amount'] += float(o.amount)
            d['weighted'] += float(o.amount) * o.probability / 100
        return out

    return Response({'by_stage': group(lambda o: o.stage),
                     'by_owner': group(lambda o: o.assigned_to.username if o.assigned_to else 'Unassigned')})