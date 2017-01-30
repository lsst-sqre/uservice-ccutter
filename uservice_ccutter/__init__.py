"""SQuaRE cookiecutter service (api.lsst.codes-compliant).
"""
from .server import server, standalone
from .projecturls import PROJECTURLS
__all__ = ["server", "standalone", "PROJECTURLS"]
