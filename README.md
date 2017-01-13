[![Build Status](https://travis-ci.org/lsst-sqre/uservice-ccutter.svg?branch=master)](https://travis-ci.org/lsst-sqre/uservice-ccutter)

# sqre-uservice-ccutter

LSST DM SQuaRE api.lsst.codes-compliant microservice wrapper for
cookiecutter projects.

## Usage

`sqre-uservice-ccutter` will run standalone on port
5000 or under `uwsgi`.  It responds to the following routes:

### Routes

* `/`: returns `OK` (used by Google Container Engine Ingress healthcheck)

* `/ccutter`: returns a JSON structure.  The keys are the types of
  projects the service knows how to make with cookiecutter, and the values
  are what cookiecutter expects to use as cookiecutter.json for that
  type of project.
  
* `/ccutter/<projecttype>`: returns a JSON structure for the named
  project type.
  
* `/ccutter/<projecttype>` (POST): accepts JSON representing a
  filled-out cookiecutter.json form.  This must be authenticated: the
  authentication headers should contain a username of the Github user
  that will be doing the project creation and commit, and the password
  field of the authentication header must contain the corresponding
  Github token.  Presuming authentication and authorization succeed, the
  POST then:
    * Substitutes additional fields in the JSON depending on the project
      type.
    * Runs cookiecutter to create the project from the template.
	* Creates a repository on Github for the project.
	* Pushes the project content to Github
  It returns a JSON structure with one field "github_repo", which
  contains the HTTPS clone url of the new repository.

### Adding new project types

To add a new project type, the developer must do the following:

1. Add the Github URL for the cookiecutter bootstrap for that type to
   `uservice_cookiecutter/projecturls.py`.
2. Create a file <typename>.py in `uservice_cookiecutter/plugins`.  For
   each field you want automatically substituted, there must be a
   function whose name is the field name, and which returns the new
   value of that field.  For instance, a `year` field should probably
   not really be user-specified, but just substitute the current year
   (which happens to be already defined in
   `uservice_ccutter.plugins.generic.current_year()`).
3. Some function that will be run each time one of these types is
   encountered (that is, a required field) must also set the fields
   `github_name`, `github_email`, and `github_repo` if they are not in
   the input JSON.
   * `github_name` is the name of the author, and an arbitrary string.
   * `github_email` is the email address of the author, and is also
     arbitrary. 
   * `github_repo` is of the form <github_org>/<github_repo>,
     e.g. `lsst-sqre/uservice-mymicroservice`.
4. Write unit tests for your field substitution in `tests`.
	 
See `uservice_ccutter/plugins/substitute.py` for more.
