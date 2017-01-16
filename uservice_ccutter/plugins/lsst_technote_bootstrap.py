#!/usr/bin/env python
"""Field-calculating plugins for lsst-technote-bootstrap.  For each
field you want substituted, make a function whose name the field name
you want to change and which takes a dictionary as input.  It should
returns the value that field should have after substitution.  Then
call the plugins substitute() function with the cookiecutter template
type as the first string argument and your
dictionary-requiring-substitution as input, and it will change the
values in that dictionary.

"""
import requests
from apikit import BackendError
from .generic import current_year


def serial_number(inputdict):
    """Find the next available serial number for the specified series."""
    series = inputdict["series"]
    # Requires that the series pick list have already been replaced with a
    #  string.
    series = series.lower()  # Should already be canonicalized, but...
    # Just scan the product list and match the series.
    # Then peel off the number.
    # We assume that a properly formatted technote *has* a number at the
    #  end of the series name.
    resp = requests.get("https://keeper.lsst.codes/products")
    if resp.status_code != 200:
        raise BackendError(status_code=resp.status_code,
                           reason=resp.reason,
                           content=resp.text)
    plist = resp.json()["products"]
    maxn = 0
    for prod in plist:
        pname = prod.split("/")[-1]
        ser = pname.split("-")[0]
        if ser != series:
            continue
        snum = pname.split("-")[-1]
        num = int(snum)
        if num > maxn:
            maxn = num
    return "%03d" % (maxn + 1)


def copyright_year(inputdict):
    """Replace copyright_year with current year"""
    _ = inputdict
    return current_year()
