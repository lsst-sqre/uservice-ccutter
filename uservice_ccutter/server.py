#!/usr/bin/env python
"""ccutter microservice framework"""
from __future__ import print_function
import json
import pprint
import os
import os.path
import time
from collections import OrderedDict
from copy import deepcopy
try:
    # Python 3
    from urllib.parse import urlparse
except ImportError:
    # Python 2
    from urlparse import urlparse
import git
from git.exc import GitCommandError
import github3
import requests
from apikit import APIFlask
from apikit import BackendError
from codekit.codetools import TempDir
from cookiecutter.main import cookiecutter
from flask import jsonify, request
from .plugins import substitute
from .projecturls import PROJECTURLS


def server(run_standalone=False):
    """Create the app and then run it."""
    # Add "/ccutter" for mapping behind api.lsst.codes
    with TempDir() as temp_dir:
        app = APIFlask(name="uservice-ccutter",
                       version="0.0.1",
                       repository="https://github.com/sqre-lsst/" +
                       "uservice-ccutter",
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
            if request.method == "GET":
                return jsonify(get_single_project_type(ptype))
            return post_request(ptype)

        def post_request(ptype):
            """Crete project: write to local repo and to GH."""
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
            retval = create_project(ptype, auth, userdict)
            return jsonify(retval)

        # pylint: disable=too-many-locals
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
                #  assumption, usually: a git repo has a unique top-level
                #  directory, and a-thing-to-be-committed-by-git is what
                #  we are using cookiecutter for.
                flist = os.listdir(tgtdir)
                if not flist:
                    raise BackendError(status_code=500,
                                       reason="Internal Server Error",
                                       content="No project created")
                gitbase = flist[0]
                gitdir = tgtdir + "/" + gitbase
                os.chdir(gitdir)
                # Create the initial (local) repository and commit the
                #  current state.
                repo = git.Repo.init(gitdir)
                allfiles = repo.untracked_files
                idx = repo.index
                idx.add(allfiles)
                # Looks like userdict should include author email....
                # We need consistent field names here...but we can
                #  synthesize them in the plugin.
                # git_name and git_email it is.
                committer = git.Actor(userdict["github_name"],
                                      userdict["github_email"])
                idx.commit("Initial commit.", author=committer,
                           committer=committer)
                # Now we need to create the repository at Github....
                #  userdict["github_repo"] must exist.
                remote_url = create_github_repository(auth, userdict)
                # Warning: NASTY
                # Set up remote config to auth correctly
                chlp = '!f() { cat > /dev/null; echo username="'
                chlp += auth["username"] + '"; echo password="'
                chlp += auth["password"] + '" }; f'
                origin = repo.create_remote("origin", url=remote_url)
                cwr = repo.config_writer()
                cwr.add_section("credential")
                cwr.set("credential", "helper", chlp)
                # https://gitpython.readthedocs.io/en/stable/tutorial.html
                #  suggests that you need to wait/sync or something?
                time.sleep(1)
                try:
                    os.sync()
                except AttributeError:
                    # Python 2 doesn't expose this.  But set() is safe there.
                    pass
                try:
                    origin.push(refspec="master:master")
                except GitCommandError:
                    raise BackendError(status_code=500,
                                       reason="Internal Server Error",
                                       content="Git push to " +
                                       userdict["github_repo"] + "failed.")
                cwr.release()
                retdict = {"repo_url": remote_url}
                return retdict

        def create_github_repository(auth, userdict):
            """Create new repo at GH."""
            ghub = github3.login(auth["username"], token=auth["password"])
            try:
                ghub.me()
            except github3.exceptions.AuthenticationFailed:
                raise BackendError(status_code=401,
                                   reason="Bad credentials",
                                   content="Github login failed.")
            namespc = userdict["github_repo"]
            org, name = namespc.split('/')
            desc = ""
            if "description" in userdict:
                desc = userdict["description"]
            gh_org = None
            for gorg in ghub.organizations():
                if gorg.login == org:
                    gh_org = gorg
                    break
            if gh_org is None:
                raise BackendError(status_code=500,
                                   reason="Internal Server Error",
                                   content=auth["username"] +
                                   " not in org " + org)
            repo = gh_org.create_repository(name, description=desc)
            if repo is None:
                raise BackendError(status_code=500,
                                   reason="Internal Server Error",
                                   content="Github repository not created")
            return repo.clone_url

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
    # pylint: disable=too-many-locals
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
