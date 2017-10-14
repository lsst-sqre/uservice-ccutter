[![Build Status](https://travis-ci.org/lsst-sqre/uservice-ccutter.svg?branch=master)](https://travis-ci.org/lsst-sqre/uservice-ccutter)

# sqre-uservice-ccutter

LSST DM SQuaRE api.lsst.codes-compliant microservice wrapper for
cookiecutter projects.

## Installation and testing

Regular installation:

```
pip install -e .
```

For development and testing:

```
pip install -e ".[dev]"
pytest
```

To make and push the Docker image:

```
make image
make docker-push
```

## Running locally

You can run the app locally for development before deploying with Kubernetes.

First, copy `test.credentials.template.sh` to `test.credentials.sh` and  fill in the environment variables:

- `SQRBOT_KEEPER_USERNAME`: the `keeper.lsst.codes` username for project admin.
- `SQRBOT_KEEPER_PASSWORD`: the `keeper.lsst.codes` password for project admin.
- `SQRBOT_LTD_KEEPER_USERNAME`: the `keeper.lsst.codes` username to embed in the technote.
- `SQRBOT_LTD_KEEPER_PASSWORD`: the `keeper.lsst.codes` password to embed in the technote.
- `SQRBOT_LTD_MASON_AWS_ID`: the AWS secret ID to embed in the technote.
- `SQRBOT_LTD_MASON_AWS_SECRET`: the AWS secret key to embed in the technote.
- `SQRBOT_USERNAME`: GitHub username.
- `SQRBOT_GITHUB_TOKEN: GitHub personal access token with these permissions:
  - `public_repo`
  - `repo:status`
  - `user`
  - `write:repo_hook`

Next, run the services in **four separate shells**:

1. `make redis` — start up the Redis container.

2. `make server` — start up the Flask app.

3. `make worker` — start up the Celery task worker.

3. `make run` — send a test `POST /ccutter/lsst-technote-bootstrap/` request.

You'll need to re-run steps 2 – 4 if you change application code (use control-C to stop the server processes).

To see the Celery task queue, start a [Flower](http://flower.readthedocs.io/en/latest/) monitor:

```
celery -A uservice_ccutter.celery_app flower
```

## HTTP Routes

* `GET /`: returns `OK` (used by Google Container Engine Ingress healthcheck)

* `GET /ccutter`: returns a JSON structure.  The keys are the types of
  projects the service knows how to make with cookiecutter, and the values
  are what cookiecutter expects to use as cookiecutter.json for that
  type of project.
  
* `GET /ccutter/<projecttype>`: returns a JSON structure for the named
  project type.
  
* `POST /ccutter/<projecttype>`: accepts JSON representing a
  filled-out cookiecutter.json form.  This must be authenticated: the
  authentication headers should contain a username of the GitHub user
  that will be doing the project creation and commit, and the password
  field of the authentication header must contain the corresponding
  GitHub token.  Presuming authentication and authorization succeed, the
  POST then:
    * Substitutes additional fields in the JSON depending on the project
      type.
    * Runs cookiecutter to create the project from the template.
	* Creates a repository on GitHub for the project.
	* Pushes the project content to GitHub

## Return Values

* If the project creation succeeds in pushing this content, the API call
  itself is guaranteed to return `200 OK`.  Prior to the push
  succeeding, the HTTP error codes you'd expect apply, notably `401
  Unauthorized` and `500 Internal Server Error`.  In essence, this means
  that putting the content on GitHub is the point of no return; after
  that, you have a project but it might require manual intervention.

* Assuming project creation returns a `200 OK`, the body of the response
  is a JSON structure with two fields: `github_repo` contains the HTTPS
  clone url of the new repository, and `post_commit_error` contains
  either `null` or a string describing any errors that occurred after
  the project was pushed to GitHub.  For a project type like an LSST
  Technote, there are several post-commit actions which each have the
  possibility of failure.  The point of `post_commit_error` is to return
  enough information to the user that it is possible to determine what
  manual actions must be taken to finish creating the project.

## Adding new project types

To add a new project type, the developer must do the following:

1. Add the GitHub URL for the cookiecutter bootstrap for that type to
   `uservice_cookiecutter/projecturls.py`.
2. Create a file `<typename>.py` in 
   `uservice_cookiecutter/plugins/projecttypes`.  For
   each field you want automatically substituted, there must be a
   function whose name is the field name, and which returns the new
   value of that field.  For instance, a `year` field should probably
   not really be user-specified, but just substitute the current year
   (which happens to be already defined in
   `uservice_ccutter.plugins.generic.current_year()`).
3. Some function that will be run each time one of these types is
   encountered (that is, a required field) must also set the fields
   `github_name`, `github_email`, and `github_repo` if they are not in
   the input JSON.  (You may wish to override even if they are.)
   * `github_name` is the name of the author, and an arbitrary string.
   * `github_email` is the email address of the author, and is also
     arbitrary. 
   * `github_repo` is of the form `<github_org>/<github_repo>`,
     e.g. `lsst-sqre/uservice-mymicroservice`.
4. `github_description` and `github_homepage` will populate those fields
     on the GitHub repository; if `github_description` does not exist
     but `description` does, `description` will be used instead.
5. Write unit tests for your field substitution in `tests`.
6. Add a `finalize_` function for work that needs to be done after
   the push to GitHub, if any.

See `uservice_ccutter/plugins/substitute.py` for more information on
field substitution.

### Function Naming Conventions

In your `<typename>.py` file, field names are mapped verbatim to
function names, except that dashes in field names are replaced with
underscores in function names, due to Python naming requirements.

Functions ending with a single underscore are reserved for use by the
plugin machinery, e.g. `finalize_`.

### The `finalize_` function

A project type may need to perform actions after its GitHub repository
has been created.  It does this in a function called `finalize_`.  If a
project type does not have any post-commit actions, it may omit the
function.  If project creation does not succeed (that is, the
template-substituted project is not successfully pushed to GitHub),
`finalize_` is never called.

If your `finalize_` function itself needs to call other functions, those
functions should be named with a single leading underscore, to protect
them from interpretation as field names.

`finalize_` itself should return None if everything went well, and a
string describing what failed if it did not completely succeed.  It
should not raise an exception.

