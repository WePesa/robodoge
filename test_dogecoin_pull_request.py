#!/usr/bin/python3

from io import BytesIO
import os
import json
import pycurl
import pygit2
import subprocess
import sys
import time
import robodoge

def get_pr(config):
    # Get PR from remote web service
    buffer = BytesIO()
    c = pycurl.Curl()
    c.setopt(c.URL, config['coordinator']['url'] + '/automerge/api/v1.0/pr/build_ready')
    c.setopt(c.USERNAME, config['http_auth']['user'])
    c.setopt(c.PASSWORD, config['http_auth']['password'])
    c.setopt(pycurl.CAINFO, '/etc/ssl/certs/428b13e3.0') # FIXME: Why isn't this found?
    c.setopt(c.WRITEDATA, buffer)
    c.perform()
    status_code = c.getinfo(c.RESPONSE_CODE)
    c.close()

    if status_code < 200 or status_code> 299:
        raise robodoge.Error("Returned status from merger coordinator was %d, expected 200-range status code" % status_code)
    prs = json.loads(buffer.getvalue().decode('UTF-8'))
    if not 'prs' in prs:
        return None

    for pr in prs['prs']:
        buffer = BytesIO()
        request = {'operation': 'claim_build'}
        c = pycurl.Curl()
        c.setopt(c.URL, config['coordinator']['url'] + '/automerge/api/v1.0/pr/' + str(pr['id']))
        c.setopt(c.POSTFIELDS, json.dumps(request))
        c.setopt(c.HTTPHEADER, ["Content-Type: application/json; charset=utf-8"])
        c.setopt(c.USERNAME, config['http_auth']['user'])
        c.setopt(c.PASSWORD, config['http_auth']['password'])
        c.setopt(pycurl.CAINFO, '/etc/ssl/certs/428b13e3.0') # FIXME: Why isn't this found?
        c.setopt(c.WRITEDATA, buffer)
        c.setopt(c.POST, 1)
        c.perform()
        status_code = c.getinfo(c.RESPONSE_CODE)
        c.close()

        if status_code < 200 or status_code> 299:
           raise robodoge.Error("Returned status from merger coordinator was %d, expected 200-range status code" % status_code)
        result = json.loads(buffer.getvalue().decode('UTF-8'))
        if 'result' in result and result['result'] == 'ok':
            return pr['number']
        else:
            print(buffer.getvalue().decode('UTF-8'))

    return None

# Script to test a single pull request from the Dogecoin repo

config = robodoge.load_configuration('config.yml')
try:
    merger = robodoge.Robodoge(config)
except robodoge.ConfigurationError as err:
    print(err.msg)
    sys.exit(1)

# Get PR from remote web service
pr_number = get_pr(config)
while pr_number:
    # Checkout Dogecoin dev branch
    path = merger.config['dogecoin_repo']['path']
    repo = merger.repo
    merger.repo.checkout(merger.safe_branch)

    # Pull from remote
    merger.repo.remotes['upstream'].fetch()

    # Check out PR branch
    pr_branch_name = 'upstream/pr/' + str(pr_number)
    pr_branch = merger.repo.lookup_branch(pr_branch_name, pygit2.GIT_BRANCH_REMOTE)
    if not pr_branch:
        print('Could not find PR branch ' + pr_branch_name)
        sys.exit(1)

    # TODO: Rebase on 1.9-dev

    # Compile and run unit tests - raises an error if this fails
    # TODO: Catch error and report gently
    robodoge.compile_dogecoin(merger.config['dogecoin_repo']['path'])

    # Upload to S3
    print('Build succeeded')
