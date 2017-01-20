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
import github3
from apikit import BackendError
from .generic import current_year

ORGHASH = {"sqr": "lsst-sqre",
           "dmtn": "lsst-dm",
           "smtn": "lsst-sims",
           "ldm": "lsst"}


def serial_number(auth, inputdict):
    """Find the next available serial number for the specified series."""
    series = inputdict["series"].lower()
    # Requires that the series pick list has already been replaced with a
    #  string.
    # Derive github_org from the series
    gh_org = ORGHASH[series]

    # scanning the product list won't work.  We need to find the next
    #  Github repo to use.

    ghub = github3.login(auth["username"], token=auth["password"])
    try:
        ghuser = ghub.me()
    except github3.exceptions.AuthenticationFailed:
        raise BackendError(status_code=401,
                           reason="Bad credentials",
                           content="Github login failed.")
    max_serial = 0
    matchstr = gh_org + "/" + series + "-"
    for repo in ghub.repositories():
        rnm = str(repo)
        if rnm.startswith(matchstr):
            serstr = rnm[(len(matchstr)):]
            try:
                sernum = int(serstr)
                if sernum > max_serial:
                    max_serial = sernum
            except ValueError:
                # We take "couldn't decode" as "not a serial"
                pass
    serial = "%03d" % (max_serial + 1)
    # Actually the same as github_namespace, but the Jinja2 substitution will
    #  not have happened yet.
    if "github_repo" not in inputdict or not inputdict["github_repo"]:
        inputdict["github_repo"] = gh_org + "/" + series + "-" + serial
    return serial


def github_org(auth, inputdict):
    """Derive Github Org from the series."""
    _ = auth
    return ORGHASH[inputdict["series"].lower()]


def copyright_year(auth, inputdict):
    """Replace copyright_year with current year."""
    _ = inputdict
    _ = auth
    return current_year()


def first_author(auth, inputdict):
    """Set canonical GH fields for project creation."""
    if "github_name" not in inputdict or not inputdict["github_name"]:
        inputdict["github_name"] = inputdict["first_author"]
    # And since we don't currently have email....
    if "github_email" not in inputdict or not inputdict["github_email"]:
        inputdict["github_email"] = "sqrbot@lsst.org"
    return inputdict["first_author"]
