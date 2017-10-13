FROM       python:3.6-slim
MAINTAINER sqre-admin
LABEL      description="Bootstrapper for cookiecutter projects" \
           name="lsstsqre/uservice-ccutter"

RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y gcc git

RUN        useradd -d /home/uwsgi -m uwsgi
RUN        mkdir /dist

# Must run python setup.py sdist first.
ARG        VERSION="0.0.9"
LABEL      version="$VERSION"
COPY       dist/sqre-uservice-ccutter-$VERSION.tar.gz /dist
RUN        pip install /dist/sqre-uservice-ccutter-$VERSION.tar.gz

USER       uwsgi
WORKDIR    /home/uwsgi
COPY       uwsgi.ini .
EXPOSE     5000
CMD        [ "uwsgi", "-T", "uwsgi.ini" ]
