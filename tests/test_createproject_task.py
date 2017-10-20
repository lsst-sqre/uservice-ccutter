from collections import OrderedDict
import os

from uservice_ccutter.tasks.createproject import (
    clone_template_repo, replace_cookiecutter_json, run_cookiecutter)


def test_clone_template_repo(tmpdir):
    clone_dir = os.path.join(str(tmpdir), 'clone_target')
    build_dir = os.path.join(str(tmpdir), '_build')

    repo_url = 'https://github.com/lsst-sqre/lsst-technote-bootstrap.git'
    clone_template_repo(repo_url, clone_dir)
    assert os.path.exists(os.path.join(clone_dir, 'cookiecutter.json'))

    template_values = OrderedDict([
        ("first_author", "Python Tester"),
        ("series", "TEST"),
        ("serial_number", "000"),
        ("title", "Document Title"),
        ("repo_name", "test-000"),
        ("github_org", "lsst-sqre-testing"),
        ("github_namespace", "lsst-sqre-testing/test-000"),
        ("docushare_url", ""),
        ("url", "test-000.lsst.io"),
        ("description", "A short description of this document"),
        ("copyright_year", "2017"),
        ("copyright_holder", "AURA"),
        ("_copy_without_render", ["*.bib"])])
    replace_cookiecutter_json(clone_dir, template_values)
    assert os.path.exists(os.path.join(clone_dir, 'cookiecutter.json'))

    project_dir = run_cookiecutter(clone_dir, build_dir)
    assert os.path.exists(project_dir)
