from django.conf import settings
from django.db import models


class AuditLog(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                             on_delete=models.SET_NULL, related_name='audit_logs')
    username = models.CharField(max_length=150, blank=True)
    action = models.CharField(max_length=30)
    entity_name = models.CharField(max_length=60, blank=True)
    record_id = models.CharField(max_length=30, blank=True)
    old_value = models.TextField(blank=True)
    new_value = models.TextField(blank=True)
    result = models.CharField(max_length=10, default='Success')
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_date = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_date']

    # append-only: no edits or deletes
    def save(self, *args, **kwargs):
        if self.pk:
            raise PermissionError('Audit records cannot be modified.')
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise PermissionError('Audit records cannot be deleted.')

    def __str__(self):
        return f'{self.created_date:%Y-%m-%d %H:%M} {self.username} {self.action}'