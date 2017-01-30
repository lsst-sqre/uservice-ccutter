#!/usr/bin/env python
"""Test substitution features for microservice.
"""
from copy import deepcopy
from uservice_ccutter.plugins import substitute
from uservice_ccutter.plugins.generic import current_year

TESTDATA = {
    "author_name": "First Last",
    "email": "me@lsst.org",
    "year": "2017",
    "svc_name": "mymicroservice",
    "version": "0.0.1",
    "repository": "https://github.com/sqre-lsst/uservice-" +
                  "{{ cookiecutter.svc_name }}",
    "description": "My api.lsst.codes microservice",
    "route": "/{{ cookiecutter.svc_name }}",
    "auth_type": "none"
}


def test_substitute_technote():
    """Test field substitution for microservices.
    """
    testdict = deepcopy(TESTDATA)
    substitute("uservice-bootstrap", None, testdict)
    changed = ["year"]
    assert testdict["year"] == current_year()
    assert testdict["github_name"] == TESTDATA["author_name"]
    assert testdict["github_email"] == TESTDATA["email"]
    ghr = "lsst-sqre/uservice-" + testdict["svc_name"]
    assert testdict["github_repo"] == ghr
    for fld in TESTDATA:
        if fld not in changed:
            assert testdict[fld] == TESTDATA[fld]
