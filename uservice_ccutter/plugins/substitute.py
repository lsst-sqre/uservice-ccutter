#!/usr/bin/env python
import importlib
import sys


def substitute(templatetype, auth, inputdict):
    """For a given type of cookiecutter template, import the correct module,
    and then for each symbol in there, apply that symbol to inputdict,
    transforming the field of the same name, and passing the auth
    structure (which holds Github credentials)."""
    ctt = "." + templatetype.lower().replace("-", "_")
    ctr = ".".join(__name__.split(".")[:-1])
    importlib.import_module(ctt, package=ctr)
    modname = ctr + ctt
    symbols = [x for x in sys.modules[modname].__dict__ if x[0] != "_"]
    rdict = {}
    for fld in inputdict:
        if fld in symbols:
            rdict[fld] = getattr(sys.modules[modname], fld)(auth, inputdict)
    for fld in rdict:
        inputdict[fld] = rdict[fld]
