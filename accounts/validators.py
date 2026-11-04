import re
from django.core.exceptions import ValidationError


class ComplexityValidator:
    def validate(self, password, user=None):
        if not (re.search(r'[A-Z]', password) and re.search(r'[a-z]', password)
                and re.search(r'\d', password) and re.search(r'[^\w\s]', password)):
            raise ValidationError(
                'Password must include an uppercase letter, a lowercase letter, '
                'a number and a special character.', code='password_complexity')

    def get_help_text(self):
        return 'Include uppercase, lowercase, a number and a special character.'