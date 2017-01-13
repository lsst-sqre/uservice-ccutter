#!/usr/bin/env python
"""Test substitution features for technotes"""
from copy import deepcopy
from uservice_ccutter.plugins import substitute
from uservice_ccutter.plugins.generic import current_year

# We cannot test serial number, because it actually requires talking to
#  Github.
TESTDATA = {
    "first_author": "Python Tester",
    "series": "SQR",
    #"serial_number": "000",
    "title": "Document Title",
    "repo_name": "{{ cookiecutter.series.lower() }}-{{ cookiecutter.serial_number }}",
    "github_org": [
        "lsst-sqre",
        "lsst-dm",
        "lsst-sims",
        "lsst"
    ],
    "github_namespace": "{{ cookiecutter.github_org }}/{{ cookiecutter.repo_name }}",
    "docushare_url": "",
    "url": "https://{{ cookiecutter.series.lower() }}-{{ cookiecutter.serial_number }}.lsst.io",
    "description": "A short description of this document",
    "copyright_year": "2016",
    "copyright_holder": "AURA/LSST"
}


def test_substitute_technote():
    """Test field substitution for technotes."""
    testdict = deepcopy(TESTDATA)
    substitute("lsst-technote-bootstrap", None, testdict)
    changed = ["github_org", "copyright_year"]
    assert testdict["github_org"] == "lsst-sqre"
    assert testdict["copyright_year"] == current_year()
    assert testdict["github_name"] == TESTDATA["first_author"]
    assert testdict["github_email"] == "sqrbot@lsst.org"
    for fld in TESTDATA:
        if fld not in changed:
            assert testdict[fld] == TESTDATA[fld]
