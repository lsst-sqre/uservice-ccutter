"""Delegate things-to-do-after-creating-repository to particular project-type
hooks.
"""
from structlog import get_logger

from .load_plugin import load_plugin


def finalize(templatetype, auth, inputdict):
    """Dispatch to particular type's finalize_ (note trailing underscore;
    the theory is that your actual fields won't end with one) function, if
    it exists.  No-op if it doesn't.

    It returns None if no errors, and a string describing the errors if
    some part of finalize_ fails.

    That implies that finalize_ for each project type should return either
    None (for success) or an error-descriptive string (for failure).  It
    should not raise an exception.
    """
    logger = get_logger()
    logger.info("Loading plugin prior to finalization", plugin=templatetype)
    module = load_plugin(templatetype)
    fname = "finalize_"
    retval = None
    if fname in module.__dict__:
        retval = getattr(module, fname)(auth, inputdict)
    return retval
