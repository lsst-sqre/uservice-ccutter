"""GitHub client utilities.
"""

__all__ = ['login_github']

import github3

from apikit import BackendError


def login_github(username, token=None):
    """Login a GitHub client.

    Parameters
    ----------
    username : `str`
        GitHub username
    token : `str`
        API token.

    Returns
    -------
    github_client : `github3.github.GitHub`
        A logged-in API client.

    Raises
    ------
    apikit.BackendError
        Raised when the login fails. Automatically returns a 401 status code.
    """
    github_client = github3.login(username, token=token)
    try:
        # Trial API call
        github_client.me()
    except (github3.exceptions.AuthenticationFailed, AttributeError):
        raise BackendError(status_code=401,
                           reason="Bad credentials",
                           content="GitHub login failed.")
    return github_client
