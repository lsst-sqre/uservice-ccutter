#!/bin/bash

source "./test.credentials.sh"

http --auth $SQRBOT_USERNAME:$SQRBOT_GITHUB_TOKEN \
    POST localhost:5000/ccutter/lsst-technote-bootstrap/ \
    title="Test technote" \
    description="This is a test" \
    series="TEST"
