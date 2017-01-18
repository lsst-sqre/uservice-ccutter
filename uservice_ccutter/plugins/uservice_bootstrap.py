#!/usr/bin/env python
"""Field-calculating plugins for uservice-bootstrap.  For each field
you want substituted, make a function whose name the field name you
want to change and which takes a dictionary as input.  It should
returns the value that field should have after substitution.  Then
call the plugins substitute() function with the cookiecutter template
type as the first string argument and your
dictionary-requiring-substitution as input, and it will change the
values in that dictionary.

"""
from .generic import current_year


def year(auth, inputdict):
    _ = inputdict
    _ = auth
    """Replace year with current year"""
    return current_year()
