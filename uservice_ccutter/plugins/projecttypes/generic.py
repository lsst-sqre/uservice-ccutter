"""Generic utility substitution functions used by multiple plugins.
"""
import datetime
from apikit import BackendError


def current_year():
    """Return current year as string."""
    return str(datetime.datetime.now().year)


def raise_ise(text):
    """Turn error text into a BackendError Internal Server Error.  Handy
    for reraising exceptions in an easy-to-consume-by-the-client form.
    """
    if isinstance(text, Exception):
        # Just in case we are exuberantly passed the entire Exception and
        #  not its textual representation.
        text = str(text)
    raise BackendError(status_code=500,
                       reason="Internal Server Error",
                       content=text)


def raise_from_req(req):
    """Turn a failed request response into a BackendError.  Handy for
    reflecting HTTP errors from farther back in the call chain."""
    if req.status_code < 400:
        # Request was successful.  Or at least, not a failure.
        return
    raise BackendError(status_code=req.status_code,
                       reason=req.reason,
                       content=req.text)
