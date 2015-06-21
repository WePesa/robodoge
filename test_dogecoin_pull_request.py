#!/usr/bin/python3

from io import BytesIO
import boto
from boto.s3.key import Key
import os
import json
import pycurl
import pygit2
import subprocess
import sys
import time
import robodoge

def report_success(config, pr, s3_arn):
    buffer = BytesIO()
    request = {'operation': 'build_success', 's3_arn': s3_arn}
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
    return result

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
        if not pr['number']:
            continue

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
            return pr

    return None

# Script to test a single pull request from the Dogecoin repo

config = robodoge.load_configuration('config.yml')
try:
    merger = robodoge.Robodoge(config)
except robodoge.ConfigurationError as err:
    print(err.msg)
    sys.exit(1)

# Get PR from remote web service
pr = get_pr(config)
while pr:
    pr_number = pr['number']
    print('Build PR #' + str(pr_number))

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
    s3 = boto.connect_s3()
    bucket = s3.get_bucket(config['s3']['bucket'])
    daemon_key = Key(bucket)
    daemon_key.key = config['s3']['client_path'] + '/' + str(pr_number) + '/dogecoind'
    daemon_key.set_contents_from_filename(config['dogecoin_repo']['path'] + '/src/dogecoind')
    daemon_key.close()

    client_key = Key(bucket)
    client_key.key = config['s3']['client_path'] + '/' + str(pr_number) + '/dogecoin-cli'
    client_key.set_contents_from_filename(config['dogecoin_repo']['path'] + '/src/dogecoin-cli')
    client_key.close()

    tx_key = Key(bucket)
    tx_key.key = config['s3']['client_path'] + '/' + str(pr_number) + '/dogecoin-tx'
    tx_key.set_contents_from_filename(config['dogecoin_repo']['path'] + '/src/dogecoin-tx')
    tx_key.close()

    # Tell the remote web service about the success
    s3_arn = 'arn:aws:s3:::' + config['s3']['bucket'] + '/' + config['s3']['client_path'] + '/' + str(pr_number) + '/dogecoind'
    report_success(config, pr, s3_arn)

    print('Build succeeded')

    pr = get_pr(config)
