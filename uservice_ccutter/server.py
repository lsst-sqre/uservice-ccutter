#!/usr/bin/env python
"""ccutter microservice framework"""
import os.path
import time
# Python 2/3 compatibility
try:
    from json.decoder import JSONDecodeError
except ImportError:
    JSONDecodeError = ValueError
try:
    # Python 3
    from urllib.parse import urlparse
except ImportError:
    # Python 2
    from urlparse import urlparse
from apikit import APIFlask
from apikit import BackendError
from codekit.codetools import TempDir
from flask import jsonify
import requests
from .projecturls import PROJECTURLS


def server(run_standalone=False):
    """Create the app and then run it."""
    # Add "/ccutter" for mapping behind api.lsst.codes
    with TempDir() as temp_dir:
        app = APIFlask(name="uservice-ccutter",
                       version="0.0.1",
                       repository="https://github.com/sqre-lsst/uservice-ccutter",
                       description="Bootstrapper for cookiecutter projects",
                       route=["/", "/ccutter"],
                       auth={"type": "none"})
        app.config["PROJECTTYPE"] = {}
        _refresh_cache(app, temp_dir, 60 * 60 * 8)

        @app.errorhandler(BackendError)
        # pylint can't understand decorators.
        # pylint: disable=unused-variable
        def handle_invalid_usage(error):
            """Custom error handler."""
            response = jsonify(error.to_dict())
            response.status_code = error.status_code
            return response

        @app.route("/")
        def healthcheck():
            """Default route to keep Ingress controller happy."""
            return "OK"

        @app.route("/ccutter")
        @app.route("/ccutter/")
        # @app.route("/ccutter/<parameter>")
        # or, if you have a parameter, def route_function(parameter=None):
        def route_function():
            """
            Bootstrapper for cookiecutter projects
            """
            # FIXME: service logic goes here
            # - raise errors as BackendError
            # - return your results with jsonify
            # - set status_code on the response as needed
            return

        if run_standalone:
            app.run(host='0.0.0.0', threaded=True)


def standalone():
    """Entry point for running as its own executable."""
    server(run_standalone=True)


def _refresh_cache(app, temp_dir, timeout):
    """Refresh cookiecutter.json cache if needed."""
    ref = temp_dir + "/last_refresh"
    now = int(time.time())
    print(temp_dir)
    if os.path.isfile(ref):
        with open(ref, "r") as rfile:
            cachedate = f.readline().rstrip("\n")
            if now - cachedate < timeout:
                return
    for purl in PROJECTURLS:
        pname = purl.split("/")[-1]
        pdir = temp_dir + "/" + pname
        if not os.path.isdir(pdir):
            os.mkdir(pdir)
        urlp = urlparse(purl)
        path = urlp.path
        ccj = "cookiecutter.json"
        rawpath = "https://raw.githubusercontent.com" + path
        rawpath += "/master/" + ccj
        print("GET %s" % rawpath)
        resp = requests.get(rawpath)
        if pname not in app.config["PROJECTTYPE"]:
            app.config["PROJECTTYPE"][pname] = {}
        if resp.status_code != 200:
            raise BackendError(reason=resp.reason,
                               status_code=resp.status_code,
                               content=resp.text)
        app.config["PROJECTTYPE"][pname] = resp.json()
        with open(pdir + "/" + ccj, "w") as wfile:
            wfile.write(resp.text)
    with open(ref, "w") as wfile:
        wfile.write("%d\n" % now)
    return

if __name__ == "__main__":
    standalone()
