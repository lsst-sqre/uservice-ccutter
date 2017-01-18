#!/usr/bin/env python
"""ccutter microservice framework"""
from copy import deepcopy
import pprint
import json
import os
import os.path
import time
try:
    # Python 3
    from urllib.parse import urlparse
except ImportError:
    # Python 2
    from urlparse import urlparse
from apikit import APIFlask
from apikit import BackendError
from codekit.codetools import TempDir
from collections import OrderedDict
from cookiecutter.main import cookiecutter
from flask import jsonify, request
from time import sleep
import git
import requests
from .plugins import substitute
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
                       auth={"type": "basic",
                             "data": {"username": "",
                                      "password": ""}})
        app.config["PROJECTTYPE"] = {}
        # Cookiecutter requires the order be preserved.
        app.config["JSON_SORT_KEYS"] = False
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
        # pylint: disable=unused-variable
        def healthcheck():
            """Default route to keep Ingress controller happy."""
            return "OK"

        @app.route("/ccutter")
        @app.route("/ccutter/")
        # pylint: disable=unused-variable
        def display_project_types():
            """Return cookiecutter.json for each project type"""
            retval = {}
            for ptype in app.config["PROJECTTYPE"]:
                retval[ptype] = get_single_project_type(ptype)
            return jsonify(retval)

        @app.route("/ccutter/<ptype>", methods=["GET", "POST"])
        @app.route("/ccutter/<ptype>/", methods=["GET", "POST"])
        # pylint: disable=unused-variable
        def action_for_type(ptype):
            """Either return the template, or create a new thing"""
            pprint.pprint(request, indent=4, width=80)
            pprint.pprint(request.method, indent=4, width=80)
            pprint.pprint(request.data, indent=4, width=80)
            pprint.pprint(request.form, indent=4, width=80)
            if request.method == "GET":
                return jsonify(get_single_project_type(ptype))
            post_request(ptype)

        def post_request(ptype):
            # Now we're POSTing.
            # We need authorization to post.  Raise error if not.
            check_authorization()
            auth = app.config["AUTH"]["data"]
            # Get data from request
            inputdict = request.get_json()
            if not inputdict:
                raise BackendError(reason="Bad Request",
                                   status_code=400,
                                   content="POST data must not be empty.")
            # We need an OrderedDict for cookiecutter to work correctly,
            # ...and we can't trust the order we get from the client, because
            #  JavaScript...
            userdict = deepcopy(app.config["PROJECTTYPE"][ptype]["template"])
            for fld in inputdict:
                userdict[fld] = inputdict[fld]
            print(userdict)
            # Here's the magic.
            substitute(ptype, auth, userdict)
            create_project(ptype, auth, userdict)
            print(userdict)
            return "OK"

        def create_project(ptype, auth, userdict):
            """Create the project"""
            cloneurl = app.config["PROJECTTYPE"][ptype]["cloneurl"]
            with TempDir() as workdir:
                clonedir = workdir + "/clonesrc"
                tgtdir = workdir + "/tgt"
                os.mkdir(clonedir)
                os.mkdir(tgtdir)
                os.chdir(tgtdir)
                git.Git().clone(cloneurl, clonedir)
                # replace cookiecutter.json
                print(workdir)
                with open(clonedir + "/cookiecutter.json", "w") as ccf:
                    ccf.write(json.dumps(userdict, indent=4))
                cookiecutter(clonedir, no_input=True)
                # Here we make the assumption that cookiecutter created
                #  a single directory.  For our projects, that is a good
                #  assumption, usually
                flist = os.listdir(tgtdir)
                if not flist:
                    raise BackendError(status_code=500,
                                       reason="Internal Server Error",
                                       content="No project created")
                gitdir = tgtdir + "/" + flist[0]
                os.chdir(gitdir)
                # Create the initial (local) repository and commit the
                #  current state.
                repo = git.Repo.init(gitdir)
                allfiles = repo.untracked_files
                idx = repo.index
                idx.add(allfiles)
                # Looks like userdict should include author email....
                committer = git.Actor(userdict["first_author"],
                                      "sqrbot@lsst.org")
                idx.commit("Initial commit.", author=committer,
                           committer=committer)
                # DEBUG
                sleep(7200)

        def get_single_project_type(ptype):
            """Return a single project type's cookiecutter.json."""
            if ptype not in app.config["PROJECTTYPE"]:
                types = [x for x in app.config["PROJECTTYPE"]]
                raise BackendError(status_code=400,
                                   reason="Bad Request",
                                   content="Project type must be one of " +
                                   str(types))
            return app.config["PROJECTTYPE"][ptype]["template"]

        def check_authorization():
            """Sets app.auth["data"] if credentials provided, raises an 
            error otherwise."""
            iauth = request.authorization
            if iauth is None:
                raise BackendError(reason="Unauthorized",
                                   status_code=401,
                                   content="No authorization provided.")
            app.config["AUTH"]["data"]["username"] = iauth.username
            app.config["AUTH"]["data"]["password"] = iauth.password

        if run_standalone:
            app.run(host='0.0.0.0', threaded=True)


def standalone():
    """Entry point for running as its own executable."""
    server(run_standalone=True)


def _refresh_cache(app, temp_dir, timeout):
    """Refresh cookiecutter.json cache if needed."""
    # pylint: disable=too-many-locals, superfluous-parens
    ref = temp_dir + "/last_refresh"
    now = int(time.time())
    print(temp_dir)
    if os.path.isfile(ref):
        with open(ref, "r") as rfile:
            cachedate = rfile.readline().rstrip("\n")
            if now - cachedate < timeout:
                return
    for purl in PROJECTURLS:
        pname = purl.split("/")[-1]
        typedir = temp_dir + "/" + pname
        if not os.path.isdir(typedir):
            os.mkdir(typedir)
        pdir = typedir + "/cctemplate"
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
        if "template" not in app.config["PROJECTTYPE"][pname]:
            app.config["PROJECTTYPE"][pname]["template"] = OrderedDict()
        if resp.status_code != 200:
            raise BackendError(reason=resp.reason,
                               status_code=resp.status_code,
                               content=resp.text)
        content = resp.content
        pprint.pprint(content)
        tdata = json.loads(content, object_pairs_hook=OrderedDict)
        app.config["PROJECTTYPE"][pname]["template"] = tdata
        pprint.pprint(tdata)
        app.config["PROJECTTYPE"][pname]["cloneurl"] = purl
        with open(pdir + "/" + ccj, "w") as wfile:
            wfile.write(resp.text)
    with open(ref, "w") as wfile:
        wfile.write("%d\n" % now)
    return

if __name__ == "__main__":
    standalone()
