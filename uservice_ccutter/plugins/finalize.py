"""Delegate things-to-do-after-creating-repository to particular project-type
hooks.
"""
from .load_plugin import load_plugin


def finalize(templatetype, auth, inputdict):
    """Dispatch to particular type's finalize_ (note trailing underscore;
    the theory is that your actual fields won't end with one) method, if
    it exists.  No-op if it doesn't.
    """
    module = load_plugin(templatetype)
    fname = "finalize_"
    if fname in module.__dict__:
        getattr(module, fname)(auth, inputdict)
