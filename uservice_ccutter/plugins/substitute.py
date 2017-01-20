"""Substitute values in incoming data"""
import importlib
import sys


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
    drive creation of the github_* fields."""
    ctt = "." + templatetype.lower().replace("-", "_")
    ctr = ".".join(__name__.split(".")[:-1])
    importlib.import_module(ctt, package=ctr)
    modname = ctr + ctt
    symbols = [x for x in sys.modules[modname].__dict__ if x[0] != "_"]
    flist = list(inputdict.keys())
    # Can't iterate over inputdict while mutating it.
    #  However, new fields we add won't be on the change-me list.
    for fld in flist:
        if fld in symbols:
            inputdict[fld] = getattr(sys.modules[modname], fld)(auth,
                                                                inputdict)
