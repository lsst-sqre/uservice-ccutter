"""Generic utility substitution functions used by multiple plugins.
"""
import datetime


def current_year():
    """Return current year as string."""
    return str(datetime.datetime.now().year)
