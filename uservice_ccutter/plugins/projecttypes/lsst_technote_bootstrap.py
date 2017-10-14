"""Field-calculating plugins for lsst-technote-bootstrap.  For each
field you want substituted, make a function whose name the field name
you want to change and which takes a dictionary as input.  It should
returns the value that field should have after substitution.  Then
call the plugins substitute() function with the cookiecutter template
type as the first string argument and your
dictionary-requiring-substitution as input, and it will change the
values in that dictionary.
"""
import os
from urllib.parse import urljoin

from celery.utils.log import get_task_logger
import git
from git.exc import GitCommandError
import requests
from travisci import TravisCI
from apikit import retry_request, raise_ise, raise_from_response

from .generic import current_year
from ...github import login_github

ORGSERIESMAP = {"sqr": "lsst-sqre",
                "dmtn": "lsst-dm",
                "smtn": "lsst-sims",
                "test": "lsst-sqre-testing"}

logger = get_task_logger(__name__)


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
    github_client = login_github(auth["username"], token=auth["password"])
    # Grab org plus series name plus dash.  Anything that starts with that
    #  is a candidate to be something in a series.
    matchstr = gh_org + "/" + series + "-"
    usedserials = []
    for repo in github_client.repositories():
        rnm = str(repo).lower()
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
    serialnum = 0
    while True:
        # Since usedserials start at zero, and count up, if our serial is
        #  the size of the usedserials list (or more, but that shouldn't
        #  happen) we just use it.  If we find, while we're getting there,
        #  that any of usedserials is not its own index (since that list
        #  is sorted), then that is the first gap, which we claim.
        #
        # This does mean that you can't reserve serial numbers anymore.  To
        #  "reserve" a serial, just create an empty document with the title
        #  you want, and go back and fill in the contents later.
        #
        # If we get more than a thousand items in a series, then the sorting
        #  is going to break, because 1000 will sort after 100 and before 101.
        #  Sorry, this seems like the least-worst option here.
        if serialnum >= len(usedserials) or \
           serialnum != usedserials[serialnum]:
            serial = "%03d" % serialnum
            break
        serialnum += 1
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
    logger.debug('finalize_ inputdict: %r', inputdict)

    logger.debug('finalize_ inputdict: %r' % inputdict)

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
        logger.info("Attempting to: %s", phases[stage])
        _update_keeper(keeper_token, inputdict)
        logger.info("Completed: %s", phases[stage])
        stage += 1

        tcli = TravisCI(github_token=auth["password"])
        logger.info("Attempting to: %s", phases[stage])
        _add_travis_webhook(tcli, inputdict)
        logger.info("Completed: %s", phases[stage])
        stage += 1

        logger.info("Attempting to: %s", phases[stage])
        _update_travis_yml(tcli, inputdict, auth["username"].upper())
        logger.info("Completed: %s", phases[stage])
        stage += 1

        logger.info("Attempting to: %s", phases[stage])
        _push_to_github(inputdict)
        logger.info("Completed: %s", phases[stage])
        stage += 1

        logger.info("Attempting to: %s", phases[stage])
        _enable_protected_branches(auth, inputdict)
        logger.info("Completed: %s", phases[stage])
        stage += 1
    except Exception as exc:
        # We actually want the overall API call to succeed, since we have
        #  successfuly created the repository, which is the point of no
        #  return
        logger.error("Exception in finalization: %s", str(exc))
        logger.error('Incomplete finalization stages: %r',
                     ', '.join(phases[stage:]))
    return retval


def _add_travis_webhook(tcli, inputdict, retries=10):
    """Enable repository for Travis CI.
    """
    def _retry_callback(n=None, remaining=None, status=None, content=None):
        """Callback for enable_travis_webhook called after each unsuccessful
        retry attempt.
        """
        logger.info('Travis webhook try %r/%r, Travis status=%r',
                    n, n + remaining, status)
        # Kick the resync endpoint again
        tcli.start_travis_sync()

    series = inputdict["series"].lower()
    slug = ORGSERIESMAP[series] + "/" + series + "-" + \
        inputdict["serial_number"]
    # Set up the retries to go for about an hour
    tcli.enable_travis_webhook(slug, retry_args={'tries': 17,
                                                 'initial_interval': 30,
                                                 'callback': _retry_callback})


def _update_travis_yml(tcli, inputdict, username):
    """Put encrypted authentication secrets into .travis.yml.
    """
    data = _generate_travis_secrets(tcli, inputdict, username)
    filename = inputdict["local_git_dir"] + "/.travis.yml"
    logger.debug("About to try to write %r", filename)
    try:
        with open(filename, "a") as travis_yml:
            travis_yml.write(data)
    except Exception as exc:
        logger.error("Exception updating .travis.yml")
        raise_ise(str(exc))


def _generate_travis_secrets(tcli, inputdict, username):
    """Map environment variables (probably set as Kubernetes secrets)
    to statements to encrypt and put into travis.yml.
    """
    keeperurl = "https://keeper.lsst.codes"
    travis_base_envvars = ["LTD_KEEPER_USER",
                           "LTD_KEEPER_PASSWORD",
                           "LTD_MASON_AWS_ID",
                           "LTD_MASON_AWS_SECRET"]
    travis_env_values = []
    for benv in travis_base_envvars:
        fullvarname = username + "_" + benv
        try:
            travis_env_values.append(os.environ[fullvarname])
        except KeyError as exc:
            raise_ise("Environment variable " + str(exc) + " must be set")
    logger.debug("All environment variables present")
    travis_env = dict(zip(travis_base_envvars, travis_env_values))
    travis_env["LTD_KEEPER_URL"] = keeperurl
    secure_env = ""
    repo = inputdict["github_repo"]

    for envkey in travis_env:
        envstr = "%s=%s" % (envkey, travis_env[envkey])
        logger.debug("Travis encrypt: %r", envkey)
        secure_env += "    - "
        secure_env += tcli.create_travis_secure_string_for_repo(repo, envstr)
        secure_env += "\n"
    return secure_env


def _get_keeper_token(tokenurl, auth):
    """Get token from keeper.lsst.codes.
    """
    uname = auth["username"].upper()
    uenv = uname + "_KEEPER_USERNAME"
    penv = uname + "_KEEPER_PASSWORD"
    try:
        kuser = os.environ[uenv]
        kpass = os.environ[penv]
    except KeyError:
        logger.error("Both %r and %r must be set", uenv, penv)
        raise_ise("Both %s and %s must be set" % (uenv, penv))
    logger.info("Requesting token from keeper.lsst.codes")
    resp = requests.get(tokenurl, auth=(kuser, kpass))
    raise_from_response(resp)
    try:
        token = resp.json()["token"]
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
    resp = requests.post(updateurl, auth=(token, ""), headers=headers,
                         json=postdata)
    raise_from_response(resp)


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
    """Enable GitHub branch protections to block on Travis CI status.

    Parameters
    ----------
    auth : `dict`
        Fields are:

        - ``username``: GitHub API username.
        - ``password``: GitHub API token.

    inputdict : `dict`
        Dictionary with required keys:

        - ``github_repo``: Name of the GitHub repo, formatted
          ``org_name/repo_name``.

    Notes
    -----
    Uses the
    ``PUT /repos/:owner/:repo/branches/:branch/protection`` GitHub API.
    https://developer.github.com/v3/repos/branches/#update-branch-protection
    """
    # The GitHub user, rather terrifyingly, claims it needs admin access in
    #  order to protect branches, but it doesn't.  If you have the permissions
    #  you need in order to create a repo in the first place and to do the
    #  Travis CI integration, you're fine.
    user = auth["username"]
    token = auth["password"]

    gh_host = "https://api.github.com"
    endpoint_path = '/repos/{github_repo}/branches/{branch}/protection'
    endpoint_path = endpoint_path.format(github_repo=inputdict['github_repo'],
                                         branch='master')
    endpoint_url = urljoin(gh_host, endpoint_path)

    headers = {
        "Accept": "application/vnd.github.v3+json",
        "Content-Type": "application/json",
    }

    data = {
        "required_status_checks": {
            "strict": True,
            "contexts": [
                "continuous-integration/travis-ci",
            ],
        },
        "enforce_admins": True,
        "required_pull_request_reviews": None,
        "restrictions": None,
    }
    logger.debug("Changing branch protection %r", endpoint_url)

    # Sometimes this, weirdly, gets a 404.  We'll wrap it in a retry
    #  loop
    resp = retry_request("put", endpoint_url, headers=headers, payload=data,
                         auth=(user, token))
    raise_from_response(resp)
