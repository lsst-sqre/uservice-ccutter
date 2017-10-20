#!/usr/bin/env python
"""Setuptools script.
"""
import os
import codecs
from setuptools import setup, find_packages

PACKAGENAME = 'sqre-uservice-ccutter'
DESCRIPTION = 'Bootstrapper for cookiecutter projects'
AUTHOR = 'Adam Thornton'
AUTHOR_EMAIL = 'athornton@lsst.org'
URL = 'https://github.com/sqre-lsst/uservice-ccutter'
VERSION = '0.1.0'
LICENSE = 'MIT'


def local_read(filename):
    """Convenience function for includes"""
    full_filename = os.path.join(
        os.path.abspath(os.path.dirname(__file__)),
        filename)
    return codecs.open(full_filename, 'r', 'utf-8').read()


LONG_DESC = local_read('README.md')

setup(
    name=PACKAGENAME,
    version=VERSION,
    description=DESCRIPTION,
    long_description=LONG_DESC,
    url=URL,
    author=AUTHOR,
    author_email=AUTHOR_EMAIL,
    license=LICENSE,
    classifiers=[
        'Development Status :: 4 - Beta',
        'Programming Language :: Python :: 3.5',
        'Programming Language :: Python :: 3.6',
        'License :: OSI Approved :: MIT License',
    ],
    keywords='lsst',
    packages=find_packages(exclude=['docs', 'tests*']),
    install_requires=[
        'sqre-apikit==0.1.2',
        'sqre-codekit==2.0.2',
        'celery[redis]==4.1.0',
        'cookiecutter==1.5.0',
        'sqre-pytravisci==0.0.4',
        'structlog>=17.2.0',
        'urllib3>=1.22',
        'uWSGI==2.0.14',
    ],
    extras_require={
        'dev': ['pytest==3.2.2',
                'pytest-flake8==0.8.1',
                'pytest-cov==2.5.1',
                'pytest-pylint==0.7.1',
                'flower',
                'httpie'],
    },
    entry_points={
        'console_scripts': []
    }
)
