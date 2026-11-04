def scope(user, qs, field='assigned_to'):
    """Admin/Manager see everything; SalesExecutive sees only their own records."""
    if user.is_sales:
        return qs.filter(**{field: user})
    return qs