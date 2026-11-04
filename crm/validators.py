from django.core.validators import RegexValidator

phone_validator = RegexValidator(
    r'^[6-9]\d{9}$', 'Enter a valid phone number.', code='invalid_phone')