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
    """Replace year with current year.
    """
    return current_year()


def author_name(auth, inputdict):
    """Set canonical GH author field for project creation.
    """
    if "github_name" not in inputdict or not inputdict["github_email"]:
        inputdict["github_name"] = inputdict["author_name"]
    return inputdict["author_name"]


def email(auth, inputdict):
    """Set canonical GH email field for project creation.
    """
    if "github_email" not in inputdict or not inputdict["github_email"]:
        inputdict["github_email"] = inputdict["email"]
    return inputdict["email"]


def svc_name(auth, inputdict):
    """Derive github_repo from svc_name.
    """
    # This happens before Jinja2 template substitution.
    if "github_repo" not in inputdict or not inputdict["github_repo"]:
        inputdict["github_repo"] = "lsst-sqre/uservice-" + \
                                   inputdict["svc_name"]
    return inputdict["svc_name"]
