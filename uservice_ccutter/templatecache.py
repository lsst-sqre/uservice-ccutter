"""Manage the cookiecutter template repo cache.
"""

__all__ = ['refresh_cache']

from collections import OrderedDict
import json
import time
from urllib.parse import urlparse

from apikit import BackendError
import requests
from structlog import get_logger

from .projecturls import PROJECTURLS


def refresh_cache(app, timeout):
    """Refresh cookiecutter.json cache if needed.
    """
    logger = get_logger()

    if "CACHETIME" not in app.config:
        app.config["CACHETIME"] = 0
    last_cache = app.config["CACHETIME"]
    now = int(time.time())
    if now - last_cache < timeout:
        return
    # Cache is older than timeout (or doesn't exist), so rebuild it.
    # Hit each of our GitHub repositories for cookiecutter projects we
    #  can build.  For each of those, retrieve the cookiecutter.json
    #  file and make it into an OrderedDict.
    # The dictionary of the cookiecutter.json files is stored in
    #  app.config["PROJECTTYPE"][type]["template"].  Where to get a project
    #  of that type is in app.config["PROJECTTYPE"][type]["cloneurl"].
    # That way, when we're asked about what a particular project type
    # needs, we only have to hit GitHub when first asked or when the
    # timeout has expired.
    logger.info("Cookiecutter cache requires refresh")
    app.config["CACHETIME"] = now
    for purl in PROJECTURLS:
        pname = purl.split("/")[-1]
        urlp = urlparse(purl)
        path = urlp.path
        ccj = "cookiecutter.json"
        rawpath = "https://raw.githubusercontent.com" + path
        rawpath += "/master/" + ccj
        logger.info("Retrieving project template", path=rawpath)
        resp = requests.get(rawpath)
        if pname not in app.config["PROJECTTYPE"]:
            app.config["PROJECTTYPE"][pname] = {}
        if "template" not in app.config["PROJECTTYPE"][pname]:
            app.config["PROJECTTYPE"][pname]["template"] = OrderedDict()
        if resp.status_code != 200:
            raise BackendError(reason=resp.reason,
                               status_code=resp.status_code,
                               content=resp.text)
        tdata = json.loads(resp.text, object_pairs_hook=OrderedDict)
        app.config["PROJECTTYPE"][pname]["template"] = tdata
        app.config["PROJECTTYPE"][pname]["cloneurl"] = purl


def get_single_project_type(app, ptype):
    """Return a single project type's cookiecutter.json.
    """
    if ptype not in app.config["PROJECTTYPE"]:
        types = [x for x in app.config["PROJECTTYPE"]]
        raise BackendError(status_code=400,
                           reason="Bad Request",
                           content="Project type must be one of " + str(types))
    return app.config["PROJECTTYPE"][ptype]["template"]
