#!/usr/bin/env python
"""Cookiecutter microservice framework.
"""
import json
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
from codekit.codetools import TempDir, get_git_credential_helper
from cookiecutter.main import cookiecutter
from cookiecutter.exceptions import CookiecutterException
from flask import jsonify, request
from .plugins import substitute, finalize
from .projecturls import PROJECTURLS


def server(run_standalone=False):
    """Create the app and then run it.
    """
    # Add "/ccutter" for mapping behind api.lsst.codes
    with TempDir() as temp_dir:
        app = APIFlask(name="uservice-ccutter",
                       version="0.0.2",
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
            """Default route to keep Ingress controller happy.
            """
            return "OK"

        @app.route("/ccutter")
        @app.route("/ccutter/")
        # pylint: disable=unused-variable
        def display_project_types():
            """Return cookiecutter.json for each project type.
            """
            retval = {}
            for ptype in app.config["PROJECTTYPE"]:
                retval[ptype] = get_single_project_type(ptype)
            return jsonify(retval)

        @app.route("/ccutter/<ptype>", methods=["GET", "POST"])
        @app.route("/ccutter/<ptype>/", methods=["GET", "POST"])
        # pylint: disable=unused-variable
        def action_for_type(ptype):
            """Either return the template, or create a new thing.
            """
            if request.method == "GET":
                return jsonify(get_single_project_type(ptype))
            return post_request(ptype)

        def post_request(ptype):
            """Create project: write to local repo and to GitHub.
            """
            # Now we're POSTing.
            # We need authorization to POST.  Raise error if not.
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
            # Here's the magic.
            substitute(ptype, auth, userdict)
            # finalize_ may need to do work with checked-out repo
            with TempDir() as workdir:
                retval = create_project(ptype, auth, userdict, workdir)
                # This is the point of no return.  We have a GitHub repo,
                #  which we must report to the user.
                # Therefore, if finalize raises an exception (it shouldn't)
                #  we must catch it and wrap it.
                pce = None
                # pylint: disable=broad-except
                try:
                    pce = finalize(ptype, auth, userdict)
                except Exception as exc:
                    # Just report error type and message.
                    pce = exc.__class__.__name__ + ": " + str(exc)
                retval["post_commit_error"] = pce
            return jsonify(retval)

        # pylint: disable=too-many-locals
        def create_project(ptype, auth, userdict, workdir):
            """Create the project.
            """
            cloneurl = app.config["PROJECTTYPE"][ptype]["cloneurl"]
            clonedir = workdir + "/clonesrc"
            tgtdir = workdir + "/tgt"
            os.mkdir(clonedir)
            os.mkdir(tgtdir)
            os.chdir(tgtdir)
            git.Git().clone(cloneurl, clonedir)
            # replace cookiecutter.json
            with open(clonedir + "/cookiecutter.json", "w") as ccf:
                ccf.write(json.dumps(userdict, indent=4))
            try:
                cookiecutter(clonedir, no_input=True)
            except (CookiecutterException, TypeError) as exc:
                raise BackendError(status_code=500,
                                   reason="Internal Server Error",
                                   content="Project creation failed: " +
                                   str(exc))
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
            userdict["local_git_dir"] = os.getcwd()
            # We need this later to modify the Travis CI configuration
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
            # Now we need to create the repository at GitHub....
            #  userdict["github_repo"] must exist.
            remote_url = create_github_repository(auth, userdict)
            # Set up remote config to auth correctly
            chlp = get_git_credential_helper(auth["username"],
                                             auth["password"])
            userdict["github_repo_url"] = remote_url
            origin = repo.create_remote("origin", url=remote_url)
            cwr = repo.config_writer()
            if not cwr.has_section("credential"):
                cwr.add_section("credential")
            cwr.set("credential", "helper", chlp)
            cwr.release()
            # https://gitpython.readthedocs.io/en/stable/tutorial.html:
            # # Please note that in python 2, writing
            # # origin.config_writer.set(...) is totally safe.
            # # In py3 __del__ calls can be delayed, thus not writing changes
            # # in time.
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
                                   userdict["github_repo"] + " failed.")
            retdict = {"repo_url": remote_url}
            return retdict

        def create_github_repository(auth, userdict):
            """Create new repo at GitHub.
            """
            ghub = github3.login(auth["username"], token=auth["password"])
            try:
                ghub.me()
            except github3.exceptions.AuthenticationFailed:
                raise BackendError(status_code=401,
                                   reason="Bad credentials",
                                   content="GitHub login failed.")
            namespc = userdict["github_repo"]
            orgname, reponame = namespc.split('/')
            desc = ""
            homepage = ""
            if "description" in userdict:
                desc = userdict["description"]
            if "github_description" in userdict:
                desc = userdict["github_description"]
            if "github_homepage" in userdict:
                homepage = userdict["github_homepage"]
            org_object = None
            # Find corresponding Organization object
            for accessible_org in ghub.organizations():
                if accessible_org.login == orgname:
                    org_object = accessible_org
                    break
            if org_object is None:
                raise BackendError(status_code=500,
                                   reason="Internal Server Error",
                                   content=auth["username"] +
                                   " not in org " + orgname)
            repo = org_object.create_repository(reponame, description=desc,
                                                homepage=homepage)
            if repo is None:
                raise BackendError(status_code=500,
                                   reason="Internal Server Error",
                                   content="GitHub repository not created")
            return repo.clone_url

        def get_single_project_type(ptype):
            """Return a single project type's cookiecutter.json.
            """
            if ptype not in app.config["PROJECTTYPE"]:
                types = [x for x in app.config["PROJECTTYPE"]]
                raise BackendError(status_code=400,
                                   reason="Bad Request",
                                   content="Project type must be one of " +
                                   str(types))
            return app.config["PROJECTTYPE"][ptype]["template"]

        def check_authorization():
            """Sets app.auth["data"] if credentials provided, raises an
            error otherwise.
            """
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
    """Entry point for running as its own executable.
    """
    server(run_standalone=True)


def _refresh_cache(app, temp_dir, timeout):
    """Refresh cookiecutter.json cache if needed.
    """
    # pylint: disable=too-many-locals
    ref = temp_dir + "/last_refresh"
    now = int(time.time())
    if os.path.isfile(ref):
        with open(ref, "r") as rfile:
            cachedate = rfile.readline().rstrip("\n")
            # If we have a last cache time newer than timeout seconds ago,
            #  just return.
            if now - cachedate < timeout:
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
        tdata = json.loads(content, object_pairs_hook=OrderedDict)
        app.config["PROJECTTYPE"][pname]["template"] = tdata
        app.config["PROJECTTYPE"][pname]["cloneurl"] = purl
        with open(pdir + "/" + ccj, "w") as wfile:
            wfile.write(resp.text)
    with open(ref, "w") as wfile:
        wfile.write("%d\n" % now)
    return


if __name__ == "__main__":
    standalone()
