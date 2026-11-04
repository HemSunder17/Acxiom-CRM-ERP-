from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from crm.models import Customer, Lead, Opportunity

User = get_user_model()


class Command(BaseCommand):
    help = 'Create demo users and sample CRM data'

    def handle(self, *a, **kw):
        specs = [('admin', 'Admin', 'Admin@12345'), ('manager1', 'Manager', 'Manager@12345'),
                 ('sales1', 'SalesExecutive', 'Sales@12345'), ('sales2', 'SalesExecutive', 'Sales@12345')]
        users = {}
        for name, role, pwd in specs:
            u, created = User.objects.get_or_create(
                username=name, defaults={'email': f'{name}@acxiom.test', 'role': role,
                                         'is_staff': role == 'Admin'})
            if created:
                u.set_password(pwd)
                u.save()
            users[name] = u
        self.stdout.write(self.style.SUCCESS('Users ready: admin / manager1 / sales1 / sales2'))

        try:
            s1, s2, adm = users['sales1'], users['sales2'], users['admin']
            c1 = Customer.objects.create(customer_name='Ravi Kumar', email='ravi@example.com',
                                         phone='9876543210', company_name='Kumar Traders', owner=s1, created_by=adm)
            c2 = Customer.objects.create(customer_name='Anita Rao', email='anita@example.com',
                                         phone='9876543211', company_name='Rao Textiles', owner=s2, created_by=adm)
            Lead.objects.create(lead_name='Suresh Babu', email='suresh@example.com', phone='9876543212',
                                company_name='Babu Foods', status='New', expected_value=50000, assigned_to=s1)
            Lead.objects.create(lead_name='Meena Iyer', email='meena@example.com', phone='9876543213',
                                company_name='Iyer Labs', status='Qualified', expected_value=120000, assigned_to=s2)
            for i, (c, st, amt, p, o) in enumerate([(c1, 'Qualification', 80000, 20, s1), (c1, 'Proposal', 150000, 50, s1),
                                                    (c2, 'Negotiation', 200000, 70, s2), (c2, 'Won', 90000, 100, s2),
                                                    (c1, 'Lost', 40000, 0, s1)]):
                Opportunity.objects.create(opportunity_name=f'Deal {i + 1}', customer=c, stage=st, amount=amt,
                                           probability=p, expected_close_date=date.today() + timedelta(days=15 * (i + 1)),
                                           assigned_to=o, created_by=adm)
            self.stdout.write(self.style.SUCCESS('Sample customers, leads and opportunities created'))
        except Exception as e:
            self.stdout.write(self.style.WARNING(f'Sample data skipped ({e}). Users are still created; add data via the UI.'))