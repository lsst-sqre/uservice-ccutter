"""Substitute values in incoming data by field.
"""
from .load_plugin import load_plugin


def substitute(templatetype, auth, inputdict):
    """For a given type of cookiecutter template, import the correct module,
    and then for each symbol in there, apply that symbol to inputdict,
    transforming the field of the same name, and passing the auth
    structure (which holds GitHub credentials).

    We expect the inputdict structure, at the end of this, to contain at
    least the following three fields: github_name, github_email, and
    github_repo.  Those will be used to create the remote repository at
    GitHub.  That does imply that any template whatsoever must have at least
    one field that's guaranteed to be present so that we can use its hook to
    drive creation of the github_* fields.
    """
    log = None
    if "_logger_" in inputdict:
        log = inputdict["_logger_"]
    if log:
        log.info("Loading plugin for %s prior to substitution" % templatetype)
    module = load_plugin(templatetype)
    symbols = [x for x in module.__dict__ if x[0] != "_" and x[-1] != "_"]
    flist = list(inputdict.keys())
    # Can't iterate over inputdict while mutating it.
    #  However, new fields we add won't be on the change-me list.
    for fld in flist:
        # Silently translate "-" to "_"
        fld = fld.replace("-", "_")
        if fld in symbols:
            inputdict[fld] = getattr(module, fld)(auth, inputdict)
