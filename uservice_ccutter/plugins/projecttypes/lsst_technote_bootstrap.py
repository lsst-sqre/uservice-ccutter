"""Field-calculating plugins for lsst-technote-bootstrap.  For each
field you want substituted, make a function whose name the field name
you want to change and which takes a dictionary as input.  It should
returns the value that field should have after substitution.  Then
call the plugins substitute() function with the cookiecutter template
type as the first string argument and your
dictionary-requiring-substitution as input, and it will change the
values in that dictionary.
"""
# pylint: disable=unused-argument
from __future__ import print_function
import base64
import os
import time
import git
from git.exc import GitCommandError
import github3
import requests
from Crypto.PublicKey import RSA
from Crypto.Cipher import PKCS1_v1_5
from apikit import BackendError
from .generic import current_year, raise_ise, raise_from_req

ORGSERIESMAP = {"sqr": "lsst-sqre",
                "dmtn": "lsst-dm",
                "smtn": "lsst-sims",
                "ldm": "lsst",
                "test": "lsst-sqre"}


def serial_number(auth, inputdict):
    """Find the next available serial number for the specified series.
    Tidy up some fields that depend on it.
    """
    series = inputdict["series"].lower()
    # Requires that the series pick list has already been replaced with a
    #  string.
    # Derive github_org from the series
    gh_org = ORGSERIESMAP[series]
    # scanning the product list won't work.  We need to find the next
    #  GitHub repo to use.
    ghub = github3.login(auth["username"], token=auth["password"])
    try:
        ghub.me()
    except github3.exceptions.AuthenticationFailed:
        raise BackendError(status_code=401,
                           reason="Bad credentials",
                           content="GitHub login failed.")
    # Grab org plus series name plus dash.  Anything that starts with that
    #  is a candidate to be something in a series.
    matchstr = gh_org + "/" + series + "-"
    usedserials = []
    for repo in ghub.repositories():
        rnm = str(repo)
        if rnm.startswith(matchstr):
            # Take whatever is after the dash as a possible serial number
            serstr = rnm[(len(matchstr)):]
            try:
                sernum = int(serstr)
                usedserials.append(sernum)
            except ValueError:
                # We take "couldn't decode" as "not a serial"
                pass
    usedserials.sort()
    serial = None
    for serialnum in range(1000):  # Serials are three digits
        # Since usedserials start at zero, and count up, if our serial is
        #  the size of the usedserials list (or more, but that shouldn't
        #  happen) we just use it.  If we find, while we're getting there,
        #  that any of usedserials is not its own index (since that list
        #  is sorted), then that is the first gap, which we claim.
        if serialnum >= len(usedserials) or \
           serialnum != usedserials[serialnum]:
            serial = "%03d" % serialnum
            break
    if serial is None:
        raise_ise("Serial numbers for series '%s' exhausted" % series)
    # Actually the same as github_namespace, but the Jinja2 substitution will
    #  not have happened yet.
    slug = series + "-" + serial
    inputdict["github_repo"] = gh_org + "/" + slug
    inputdict["github_homepage"] = "https://" + slug + ".lsst.io"
    return serial


def title(auth, inputdict):
    """Set GitHub description from title, not description.  Leave
    title (and Britney) alone.
    """
    inputdict["github_description"] = inputdict["title"]
    return inputdict["title"]


def github_org(auth, inputdict):
    """Derive GitHub Org from the series.
    """
    return ORGSERIESMAP[inputdict["series"].lower()]


def copyright_year(auth, inputdict):
    """Replace copyright_year with current year.
    """
    return current_year()


def first_author(auth, inputdict):
    """Set canonical GH fields for project creation.
    """
    if "github_name" not in inputdict or not inputdict["github_name"]:
        inputdict["github_name"] = inputdict["first_author"]
    # And since we don't currently have email....
    if "github_email" not in inputdict or not inputdict["github_email"]:
        inputdict["github_email"] = "sqrbot@lsst.org"
    return inputdict["first_author"]


def finalize_(auth, inputdict):
    """Register with Keeper.

    This requires some environment variables to be set.  The first
    token in the environment variable (before the first underscore) is
    the username that comes in as auth["username"], uppercased.  Let's
    pretend that is 'SQRBOT', because it usually will be.  Then
    'SQRBOT_KEEPER_USERNAME' and 'SQRBOT_KEEPER_PASSWORD' must be set
    in the environment in order to update LSST The Docs.

    It gets worse.  'SQRBOT_LTD_MASON_AWS_ID' and
    'SQRBOT_LTD_MASON_AWS_SECRET' must be set too, as well as
    'SQRBOT_LTD_KEEPER_USER' and 'SQRBOT_LTD_KEEPER_PASSWORD'.
    Those last two are distinct from the first two keeper variables.
    Also note that it's 'USER', not 'USERNAME' there, for reasons related
    to how Travis is making use of those environment variables.

    This is very clumsy and means, basically, you need one set of six
    environment variables per user.  But we certainly do not want to
    let unauthenticated users poke the API.

    This is a pretty good argument for Vault or something like it.

    """
    tokenurl = "https://keeper.lsst.codes/token"
    keeper_token = _get_keeper_token(tokenurl, auth)
    stage = 0
    # pylint: disable=bad-continuation
    phases = ["Update LTD keeper with new technote",
              "Add Travis CI webhook",
              "Update .travis.yml with secrets",
              "Push updated .travis.yml to GitHub",
              "Protect 'master' branch at GitHub",
              ]
    retval = None
    try:
        _update_keeper(keeper_token, inputdict)
        stage += 1
        _add_travis_webhook(auth, inputdict)
        stage += 1
        _update_travis_yml(auth, inputdict)
        stage += 1
        _push_to_github(inputdict)
        stage += 1
        _enable_protected_branches(auth, inputdict)
        stage += 1
    except BackendError as exc:
        # We actually want the overall API call to succeed, since we have
        #  successfuly created the repository, which is the point of no
        #  return
        _debug("received BackendError: %s" % str(exc))
        error_content = "BackendError:\n"
        error_content += str(exc.status_code) + " " + exc.reason + ":\n"
        error_content += str(exc.content)
        retval = "Post-commit finalization failed. Stages that did not"
        retval += " complete correctly:\n"
        retval += "\n".join(phases[stage:])
        retval += "\nError content was:\n"
        retval += error_content
        _debug(retval)
    return retval


# Travis functions adapted from https://github.com/lsst-sqre/travis-encrypt
# Forked from https://github.com/sivel/travis-encrypt
# Thanks to Matt Martz

# All the leading underscores are to protect these from substitute().
# We want them to be defined at the top level so we can get at them for
# unit tests.


def _get_travis_key(repo, token):
    """Retrieve public key from travis repo.
    """
    keyurl = "https://api.travis-ci.org/repos/%s/key" % repo
    # pylint: disable=broad-except, bad-continuation
    headers = {"Authorization": "token " + token,
               "Content-Type": "application/json",
               "Accept": "application/vnd.travis-ci.2+json",
               "User-Agent": "TravisTechnoteAPI/0.1.0"
               }
    req = _retry_request("get", keyurl, headers=headers)
    raise_from_req(req)
    try:
        keyjson = req.json()
    except Exception as exc:
        raise_ise(str(exc))
    pubkey = keyjson.get("key")
    return pubkey


def _travis_encrypt(repo, data, public_key):
    """Encrypt data with travis public key.
    """
    key = RSA.importKey(public_key)
    cipher = PKCS1_v1_5.new(key)
    _debug("Attempting encryption of string.")
    # Python 2/3
    try:
        bdata = bytes(data, "utf8")
    except TypeError:
        bdata = bytes(data)
    retval = base64.b64encode(cipher.encrypt(bdata)).decode("utf8")
    _debug("Encryption succeeded.")
    return retval


def _travis_secure_string(repo, data, public_key):
    """Create encrypted entry for travis.yml.
    """
    encstring = _travis_encrypt(repo, data, public_key)
    return "secure: \"%s\"" % encstring


# pylint: disable=too-many-locals
def _generate_travis_secrets(auth, inputdict):
    """Map environment variables (probably set as Kubernetes secrets)
    to statements to encrypt and put into travis.yml."""
    _debug("Encrypting environment variables")
    token = auth["travis_token"]
    del auth["travis_token"]
    keeperurl = "https://keeper.lsst.codes"
    travis_base_envvars = ["LTD_KEEPER_USER",
                           "LTD_KEEPER_PASSWORD",
                           "LTD_MASON_AWS_ID",
                           "LTD_MASON_AWS_SECRET"]
    uname = auth["username"].upper()
    travis_env_values = []
    for benv in travis_base_envvars:
        fullvarname = uname + "_" + benv
        try:
            travis_env_values.append(os.environ[fullvarname])
        except KeyError as exc:
            raise_ise("Environment variable " + str(exc) + " must be set")
    _debug("All environment variables present")
    travis_env = dict(zip(travis_base_envvars, travis_env_values))
    travis_env["LTD_KEEPER_URL"] = keeperurl
    secure_env = ""
    repo = inputdict["github_repo"]
    public_key = _get_travis_key(repo, token)
    for envkey in travis_env:
        envstr = "%s=%s" % (envkey, travis_env[envkey])
        _debug("About to encrypt %s" % envkey)
        secure_env += "    - " + _travis_secure_string(repo, envstr,
                                                       public_key)
        secure_env += "\n"
    return secure_env


def _update_travis_yml(auth, inputdict):
    _debug("Beginning .travis.yml update")
    data = _generate_travis_secrets(auth, inputdict)
    filename = inputdict["local_git_dir"] + "/.travis.yml"
    _debug("About to try to write %s" % filename)
    # pylint: disable=broad-except
    try:
        with open(filename, "a") as travis_yml:
            travis_yml.write(data)
    except Exception as exc:
        _debug("Received exception: %s: %s", (exc.__class__.__name__,
                                              str(exc)))
        raise_ise(str(exc))
    _debug(".travis.yml updated")


def _get_keeper_token(tokenurl, auth):
    uname = auth["username"].upper()
    uenv = uname + "_KEEPER_USERNAME"
    penv = uname + "_KEEPER_PASSWORD"
    try:
        kuser = os.environ[uenv]
        kpass = os.environ[penv]
    except KeyError:
        raise_ise("Both %s and %s must be set" % (uenv, penv))
    req = requests.get(tokenurl, auth=(kuser, kpass))
    raise_from_req(req)
    # pylint: disable=broad-except
    try:
        token = req.json()["token"]
    except Exception as exc:
        raise_ise(str(exc))
    return token


def _update_keeper(token, inputdict):
    """Update keeper with new product.
    """
    updateurl = "https://keeper.lsst.codes/products/"
    slug = inputdict["series"].lower() + "-" + inputdict["serial_number"]
    postdata = {
        "bucket_name": "lsst-the-docs",
        "doc_repo": inputdict["github_repo_url"],
        "root_domain": "lsst.io",
        "root_fastly_domain": "n.global-ssl.fastly.net",
        "slug": slug,
        "title": inputdict["title"]
    }
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json"
    }
    req = requests.post(updateurl, auth=(token, ""), headers=headers,
                        json=postdata)
    raise_from_req(req)


def _add_travis_webhook(auth, inputdict):
    """Enable repository for Travis CI.
    """
    # pylint: disable=too-many-locals
    travis_host = "https://api.travis-ci.org"
    travis_headers = {
        "Content-Type": "application/json",
        "Accept": "application/vnd.travis-ci.2+json",
        "User-Agent": "TravisTechnoteAPI/0.1.0"
    }
    github_token = auth["password"]
    travis_token = _exchange_token(github_token, travis_headers)
    auth["travis_token"] = travis_token
    travis_headers["Authorization"] = "token " + travis_token
    sync_url = travis_host + "/users/sync"
    # Start sync
    req = requests.post(sync_url, headers=travis_headers)
    if req.status_code == 409:
        # 409 is "already syncing"; so we pretend it was ours.
        req.status_code = 200
    raise_from_req(req)
    _debug("Travis CI <-> GitHub Sync started")
    series = inputdict["series"].lower()
    slug = ORGSERIESMAP[series] + "/" + series + "-" + \
        inputdict["serial_number"]
    # Retry until repo is ready
    user_url = travis_host + "/repos/" + slug
    req = _retry_request("get", user_url, headers=travis_headers)
    # Get the ID and flip the switch
    # pylint: disable=broad-except
    try:
        repo_id = req.json()["repo"]["id"]
    except Exception as exc:
        raise_ise(str(exc))
    _debug("GitHub Repository ID: %s" % repo_id)
    hook_url = travis_host + "/hooks"
    hook = {
        "hook": {
            "id": repo_id,
            "active": True
        }
    }
    req = _retry_request("put", hook_url, headers=travis_headers,
                         payload=hook)
    raise_from_req(req)


# pylint: disable = too-many-locals, too-many-arguments
def _retry_request(method, url, headers=None, payload=None, auth=None,
                   tries=10, initial_interval=5):
    """Retry an HTTP request with linear backoff."""
    _debug("Beginning to wait for request %s %s" % (method, url))
    method = method.lower()
    attempt = 1
    while True:
        if method == "get":
            req = requests.get(url, headers=headers, params=payload,
                               auth=auth)
        elif method == "put" or method == "post":
            req = requests.put(url, headers=headers, json=payload, auth=auth)
        else:
            raise_ise("Bad method %s: must be 'get', 'put', or 'post" %
                      method)
        if req.status_code == 200:
            break
        _debug("%s %s failed %d/%d" % (method, url, attempt, tries))
        delay = initial_interval * attempt
        if attempt == tries:
            raise_ise("Failed to sync Travis CI with GitHub after %d tries." %
                      tries)
        _debug("Waiting %d seconds." % delay)
        time.sleep(delay)
        attempt += 1
    _debug("Completed wait for request %s %s" % (method, url))
    return req


def _exchange_token(github_token, headers):
    travis_host = "https://api.travis-ci.org"
    travis_token_url = travis_host + "/auth/github"
    postdata = {
        "github_token": github_token
    }
    _debug("Exchanging GitHub token for Travis CI token")
    req = requests.post(travis_token_url, headers=headers, json=postdata)
    raise_from_req(req)
    # pylint: disable=broad-except
    try:
        rdata = req.json()
    except Exception as exc:
        raise_ise(str(exc))
    access_token = rdata.get("access_token")
    if not access_token:
        raise BackendError(status_code=403,
                           reason="Forbidden",
                           content="Unable to get Travis CI access token")
    _debug("Travis CI token acquired")
    return access_token


def _push_to_github(inputdict):
    repo = git.Repo(inputdict["local_git_dir"])
    idx = repo.index
    committer = git.Actor(inputdict["github_name"],
                          inputdict["github_email"])
    idx.add([".travis.yml"])
    idx.commit("Added Travis CI configuration.",
               author=committer, committer=committer)
    origin = repo.remote()
    try:
        origin.push(refspec="master:master")
    except GitCommandError:
        raise_ise("Git push to %s failed" % inputdict["github_repo"])


def _enable_protected_branches(auth, inputdict):
    # https://developer.github.com/v3/repos/branches/
    # Currently (February 1, 2017) experimental
    gh_host = "https://api.github.com"
    # The GitHub user, rather terrifyingly, claims it needs admin access in
    #  order to protect branches, but it doesn't.  If you have the permissions
    #  you need in order to create a repo in the first place and to do the
    #  Travis CI integration, you're fine.
    user = auth["username"]
    token = auth["password"]
    prot_path = "/repos/" + inputdict["github_repo"] + \
        "/branches/master/protection"
    prot_url = gh_host + prot_path
    headers = {
        "Accept": "application/vnd.github.loki-preview+json",
        "Content-Type": "application/json",
    }
    data = {
        "required_status_checks": {
            "include_admins": True,
            "strict": True,
            "contexts": [
                "continuous-integration/travis-ci",
            ],
        },
        "required_pull_request_reviews": None,
        "restrictions": None,
    }
    _debug("Changing protection with URL %s" % prot_url)
    # Sometimes this, weirdly, gets a 404.  We'll wrap it in a retry
    #  loop
    req = _retry_request("put", prot_url, headers=headers, payload=data,
                         auth=(user, token))
    raise_from_req(req)


def _debug(*args):
    if os.environ.get("DEBUG"):
        print(*args)
