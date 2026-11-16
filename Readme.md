# AcxiomCRM
Role-based CRM (Admin / Manager / Sales Executive) built with Django, Django REST Framework, SQLite, Bootstrap 5 and Chart.js.

**Note on framework:** the specification references ASP.NET Core; this implementation uses the Django equivalents
(AbstractUser + PBKDF2 hashing instead of Identity, CSRF middleware instead of ValidateAntiForgeryToken,
Django ORM instead of EF Core, DRF serializers instead of DTOs).

## Run
    python -m venv venv && source venv/bin/activate
    pip install django djangorestframework
    python manage.py migrate
    python manage.py seed
    python manage.py runserver

## Demo accounts
admin / Hem@1234, Hem/ Hem@1234

## Features
Authentication with password policy and lockout, role-based server-side scoping, CRUD for Customers, Leads,
Opportunities, Follow-Ups and Activities, lead conversion workflow, client and server validation, business rules,
audit log with filters, Users & Roles admin, dashboard with Chart.js, REST API (/api/customers, /api/leads,
/api/opportunities, /api/reports/pipeline, /api/auth/login, /api/auth/logout).
