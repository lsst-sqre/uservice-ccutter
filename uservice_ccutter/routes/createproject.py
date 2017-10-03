__all__ = ['create_project']

import os
from copy import deepcopy
import json
import time

from apikit import BackendError
from codekit.codetools import TempDir, get_git_credential_helper
from cookiecutter.main import cookiecutter
from cookiecutter.exceptions import CookiecutterException
from flask import jsonify, request, current_app
import git
from git.exc import GitCommandError
from structlog import get_logger

from . import api
from ..github import login_github
from ..plugins import substitute, finalize


@api.route("/ccutter/<ptype>", methods=["POST"])
@api.route("/ccutter/<ptype>/", methods=["POST"])
def create_project(ptype):
    """Create a new project.
    """
    # We need authorization to POST.  Raise error if not.
    check_authorization()
    auth = current_app.config["AUTH"]["data"]
    # Get data from request
    inputdict = request.get_json()
    if not inputdict:
        raise BackendError(reason="Bad Request",
                           status_code=400,
                           content="POST data must not be empty.")
    # We need an OrderedDict for cookiecutter to work correctly,
    # ...and we can't trust the order we get from the client, because
    #  JavaScript...
    userdict = deepcopy(current_app.config["PROJECTTYPE"][ptype]["template"])
    for fld in inputdict:
        userdict[fld] = inputdict[fld]
    # Here's the magic.
    substitute(ptype, auth, userdict)
    # finalize_ may need to do work with checked-out repo
    with TempDir() as workdir:
        retval = make_project(ptype, auth, userdict, workdir)
        # This is the point of no return.  We have a GitHub repo,
        #  which we must report to the user.
        # Therefore, if finalize raises an exception (it shouldn't)
        #  we must catch it and wrap it.
        pce = None
        try:
            pce = finalize(ptype, auth, userdict)
        except Exception as exc:
            # Just report error type and message.
            pce = exc.__class__.__name__ + ": " + str(exc)
        retval["post_commit_error"] = pce
        return jsonify(retval)


def check_authorization():
    """Sets app.auth["data"] if credentials provided, raises an
    error otherwise.
    """
    logger = get_logger()
    iauth = request.authorization
    if iauth is None:
        raise BackendError(reason="Unauthorized",
                           status_code=401,
                           content="No authorization provided.")
    current_app.config["AUTH"]["data"]["username"] = iauth.username
    current_app.config["AUTH"]["data"]["password"] = iauth.password
    logger = logger.bind(username=iauth.username)


def make_project(ptype, auth, userdict, workdir):
    """Create the project.
    """
    cloneurl = current_app.config["PROJECTTYPE"][ptype]["cloneurl"]
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
    github_client = login_github(auth['username'], token=auth["password"])
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
    for accessible_org in github_client.organizations():
        if accessible_org.login == orgname:
            org_object = accessible_org
            break
    if org_object is None:
        raise BackendError(status_code=500,
                           reason="Internal Server Error",
                           content=auth["username"] + "not in org " + orgname)
    repo = org_object.create_repository(reponame, description=desc,
                                        homepage=homepage)
    if repo is None:
        raise BackendError(status_code=500,
                           reason="Internal Server Error",
                           content="GitHub repository not created")
    return repo.clone_url
