#!/usr/bin/python3

import os
import pygit2
import subprocess
import sys
import time
import robodoge

# Script to test a single pull request from the Dogecoin repo

config = robodoge.load_configuration('config.yml')
try:
    merger = robodoge.Robodoge(config)
except robodoge.ConfigurationError as err:
    print(err.msg)
    sys.exit(1)

# Get PR from remote web service
pr_number = 1153
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

# Report go/no go back to the web service
