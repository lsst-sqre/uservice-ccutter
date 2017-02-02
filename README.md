[![Build Status](https://travis-ci.org/lsst-sqre/uservice-ccutter.svg?branch=master)](https://travis-ci.org/lsst-sqre/uservice-ccutter)

# sqre-uservice-ccutter

LSST DM SQuaRE api.lsst.codes-compliant microservice wrapper for
cookiecutter projects.

## Usage

`sqre-uservice-ccutter` will run standalone on port
5000 or under `uwsgi`.  It responds to the following routes:

### Routes

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

It returns a JSON structure with two fields: `github_repo`
  contains the HTTPS clone url of the new repository, and 
  `post_commit_error` contains either `null` or a string describing any
  errors that occurred after the project was pushed to GitHub.


### Adding new project types

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

#### Function Naming Conventions

In your `<typename>.py` file, field names are mapped verbatim to
function names, except that dashes in field names are replaced with
underscores in function names, due to Python naming requirements.

Functions ending with a single underscore are reserved for use by the
plugin machinery, e.g. `finalize_`.

#### The `finalize_` function

A project type may need to perform actions after its GitHub repository
has been created.  It does this in a function called `finalize_`.  If a
project type does not have any post-commit actions, it may omit the
function.

If your `finalize_` function itself needs to call other functions, those
functions should be named with a single leading underscore, to protect
them from interpretation as field names.

`finalize_` itself should return None if everything went well, and a
string describing what failed if it did not completely succeed.  It
should not raise an exception.

