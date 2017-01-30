"""Field-calculating plugins for lsst-technote-bootstrap.  For each
field you want substituted, make a function whose name the field name
you want to change and which takes a dictionary as input.  It should
returns the value that field should have after substitution.  Then
call the plugins substitute() function with the cookiecutter template
type as the first string argument and your
dictionary-requiring-substitution as input, and it will change the
values in that dictionary.
"""
# pylint: disable=unused-argument
import github3
from apikit import BackendError
from .generic import current_year

ORGSERIESMAP = {"sqr": "lsst-sqre",
                "dmtn": "lsst-dm",
                "smtn": "lsst-sims",
                "ldm": "lsst",
                "test": "lsst-sqre"}


def serial_number(auth, inputdict):
    """Find the next available serial number for the specified series."""
    series = inputdict["series"].lower()
    # Requires that the series pick list has already been replaced with a
    #  string.
    # Derive github_org from the series
    gh_org = ORGSERIESMAP[series]
    # scanning the product list won't work.  We need to find the next
    #  GitHub repo to use.
    ghub = github3.login(auth["username"], token=auth["password"])
    try:
        ghub.me()
    except github3.exceptions.AuthenticationFailed:
        raise BackendError(status_code=401,
                           reason="Bad credentials",
                           content="GitHub login failed.")
    # Grab org plus series name plus dash.  Anything that starts with that
    #  is a candidate to be something in a series.
    matchstr = gh_org + "/" + series + "-"
    usedserials = []
    for repo in ghub.repositories():
        rnm = str(repo)
        if rnm.startswith(matchstr):
            # Take whatever is after the dash as a possible serial number
            serstr = rnm[(len(matchstr)):]
            try:
                sernum = int(serstr)
                usedserials.append(sernum)
            except ValueError:
                # We take "couldn't decode" as "not a serial"
                pass
    usedserials.sort()
    serial = None
    for serialnum in range(1000):  # Serials are three digits
        # Since usedserials start at zero, and count up, if our serial is
        #  the size of the usedserials list (or more, but that shouldn't
        #  happen) we just use it.  If we find, while we're getting there,
        #  that any of usedserials is not its own index (since that list
        #  is sorted), then that is the first gap, which we claim.
        if serialnum >= len(usedserials) or \
           serialnum != usedserials[serialnum]:
            serial = "%03d" % serialnum
            break
    if serial is None:
        raise BackendError(status_code=500,
                           reason="Internal Server Error",
                           content="Serial numbers for " +
                           "series '%s' exhausted" % series)
    # Actually the same as github_namespace, but the Jinja2 substitution will
    #  not have happened yet.
    inputdict["github_repo"] = gh_org + "/" + series + "-" + serial
    return serial


def github_org(auth, inputdict):
    """Derive GitHub Org from the series."""
    return ORGSERIESMAP[inputdict["series"].lower()]


def copyright_year(auth, inputdict):
    """Replace copyright_year with current year."""
    return current_year()


def first_author(auth, inputdict):
    """Set canonical GH fields for project creation."""
    if "github_name" not in inputdict or not inputdict["github_name"]:
        inputdict["github_name"] = inputdict["first_author"]
    # And since we don't currently have email....
    if "github_email" not in inputdict or not inputdict["github_email"]:
        inputdict["github_email"] = "sqrbot@lsst.org"
    return inputdict["first_author"]


def finalize_(auth, inputdict):
    """Register with Keeper."""
    pass
