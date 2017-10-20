__all__ = ['create_project_as_task']

import json
from collections import OrderedDict
import contextlib
import os
import time

from celery.utils.log import get_task_logger
from codekit.codetools import TempDir, get_git_credential_helper
from cookiecutter.main import cookiecutter
from cookiecutter.exceptions import CookiecutterException
import git
from git.exc import GitCommandError
from flask import current_app

from ..celeryapp import celery_app
from ..github import login_github
from ..plugins import substitute, finalize

logger = get_task_logger(__name__)


@celery_app.task
def create_project_as_task(project_type, auth, template_values_str):
    """Create a project repository (intended to operate as an async Celery
    task.
    """
    template_values = json.loads(template_values_str,
                                 object_pairs_hook=OrderedDict)
    logger.info('Creating a project of type %r', project_type)

    logger.debug('Template before substitute: %r', template_values)

    # Use project type plugin to fully compute template values based on
    # defaults and user inputs already in template_values
    substitute(project_type, auth, template_values)

    logger.debug('Template after substitute: %r', template_values)

    # finalize_ may need to do work with checked-out repo
    with TempDir() as workdir:
        template_repo_dir = os.path.join(workdir, '_template_src')
        clone_template_repo(
            current_app.config["PROJECTTYPE"][project_type]["cloneurl"],
            template_repo_dir)

        replace_cookiecutter_json(template_repo_dir, template_values)

        build_dir = os.path.join(workdir, '_build')
        if not os.path.exists(build_dir):
            os.makedirs(build_dir)
        project_dir = run_cookiecutter(template_repo_dir, build_dir)

        # Store project_dir for finalize()
        template_values["local_git_dir"] = project_dir

        init_repo(project_dir, template_values)

        logger.info('Creating GitHub repository')
        github_remote_url = create_github_repository(auth, template_values)
        template_values["github_repo_url"] = github_remote_url

        push_to_github(project_dir, github_remote_url, auth)

        # retval = make_project(project_type, auth, template_values, workdir)
        # This is the point of no return.  We have a GitHub repo,
        #  which we must report to the user.
        # Therefore, if finalize raises an exception (it shouldn't)
        #  we must catch it and wrap it.
        post_commit_error = finalize(project_type, auth, template_values)

    logger.info('Finalize return value: %s', post_commit_error)
    logger.info('Finished creating the project')


def clone_template_repo(repo_url, template_repo_dir):
    logger.info('Cloning template repo')
    os.mkdir(template_repo_dir)
    git.Git().clone(repo_url, template_repo_dir)


def replace_cookiecutter_json(template_repo_dir, template_values):
    logger.info('Setting up cookiecutter.json')
    json_path = os.path.join(template_repo_dir, 'cookiecutter.json')
    with open(json_path, "w") as f:
        f.write(json.dumps(template_values, indent=4))


def run_cookiecutter(template_repo_dir, target_dir):
    logger.info('Running cookiecutter')
    if not os.path.exists(target_dir):
        os.makedirs(target_dir)
    with change_dir(target_dir):
        try:
            cookiecutter(template_repo_dir, no_input=True)
        except (CookiecutterException, TypeError) as exc:
            raise RuntimeError("Project creation failed: " + str(exc))

    # Here we make the assumption that cookiecutter created
    #  a single directory.  For our projects, that is a good
    #  assumption, usually: a git repo has a unique top-level
    #  directory, and a-thing-to-be-committed-by-git is what
    #  we are using cookiecutter for.
    try:
        project_dir = os.path.join(target_dir, os.listdir(target_dir)[0])
    except Exception:
        raise RuntimeError('No project created')
    return project_dir


def init_repo(project_dir, template_values):
    logger.info('Initializing git repo')
    # FIXME necessary to cd into project_dir?
    # We need this later to modify the Travis CI configuration
    # Create the initial (local) repository and commit the
    #  current state.
    repo = git.Repo.init(project_dir)
    repo.index.add(repo.untracked_files)
    # Looks like template_values should include author email....
    # We need consistent field names here...but we can
    #  synthesize them in the plugin.
    # git_name and git_email it is.
    committer = git.Actor(template_values["github_name"],
                          template_values["github_email"])
    repo.index.commit("Initial commit.",
                      author=committer,
                      committer=committer)
    # Now we need to create the repository at GitHub....
    #  template_values["github_repo"] must exist.


def create_github_repository(auth, template_values):
    """Create new repo at GitHub.
    """
    logger.info('Creating the GitHub repository %r with user %r',
                template_values["github_repo"], auth['username'])
    github_client = login_github(auth['username'], token=auth["password"])
    namespc = template_values["github_repo"]
    orgname, reponame = namespc.split('/')
    desc = ""
    homepage = ""
    if "description" in template_values:
        desc = template_values["description"]
    if "github_description" in template_values:
        desc = template_values["github_description"]
    if "github_homepage" in template_values:
        homepage = template_values["github_homepage"]
    org_object = None
    # Find corresponding Organization object
    for accessible_org in github_client.organizations():
        if accessible_org.login == orgname:
            org_object = accessible_org
            break
    if org_object is None:
        raise RuntimeError(auth["username"] + "not in org " + orgname)
    repo = org_object.create_repository(reponame, description=desc,
                                        homepage=homepage)
    if repo is None:
        raise RuntimeError(content="GitHub repository not created")
    return repo.clone_url


def push_to_github(project_dir, remote_url, auth):
    logger.info('Pushing to GitHub')
    repo = git.Repo(project_dir)

    # Set up remote config to auth correctly
    cred_helper = get_git_credential_helper(auth["username"],
                                            auth["password"])
    origin = repo.create_remote("origin", url=remote_url)
    config_writer = repo.config_writer()
    if not config_writer.has_section("credential"):
        config_writer.add_section("credential")
        config_writer.set("credential", "helper", cred_helper)
    config_writer.release()
    # https://gitpython.readthedocs.io/en/stable/tutorial.html:
    # # Please note that in python 2, writing
    # # origin.config_writer.set(...) is totally safe.
    # # In py3 __del__ calls can be delayed, thus not writing changes
    # # in time.
    #  suggests that you need to wait/sync or something?
    time.sleep(1)
    os.sync()

    try:
        origin.push(refspec="master:master")
    except GitCommandError:
        raise RuntimeError("Git push to {} failed".format(remote_url))


@contextlib.contextmanager
def change_dir(target_dir):
    """Temporarily change to the `target_dir` directory inside a managed
    context.

    Parameters
    ----------
    target-dir : `str`
        Directory to change into within the context.
    """
    prev_dir = os.getcwd()
    try:
        os.chdir(target_dir)
        yield
    finally:
        os.chdir(prev_dir)
