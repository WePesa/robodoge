#!/usr/bin/python3

import os
import pygit2
import subprocess
import sys
import time
import robodoge

# Script to test a single pull request from the Dogecoin repo

def test_pr_merge(conn, merger, pr_id):
    """
    Test if a pull request can be cleanly merged against the current development branch. Returns true/false
    """

    path = merger.config['dogecoin_repo']['path']
    repo = merger.repo

    # Test if the branch exists already, create it if not
    head_branch = merger.create_branch('bitcoin-pr-%d' % pr_id)
    if not head_branch:
        return False
    try:
        repo.checkout(head_branch)

        if not merger.apply_pull_requests(conn, head_branch, [pr_id]):
            return False

        # Make sure it's a viable build too
        print('Attempting compilation of PR %d' % pr_id)
        try:
            robodoge.compile_dogecoin(path)
        except robodoge.BuildError:
            return False
    finally:
        repo.checkout(merger.safe_branch)
        repo.lookup_branch(head_branch.branch_name, pygit2.GIT_BRANCH_LOCAL).delete()

    return True

pr_number = 1153
config = robodoge.load_configuration('config.yml')
try:
    merger = robodoge.Robodoge(config)
except robodoge.ConfigurationError as err:
    print(err.msg)
    sys.exit(1)

# Load the pull request number from the API
# Checkout Dogecoin dev branch
# Pull from remote
# Check put PR branch
# Rebase on 1.9-dev
# Compile
# Run unit tests
# Upload to S3
# Report go/no go

        if test_pr_merge(conn, merger, pr_id):
            viable_pr_ids.append(pr_id)
        if len(viable_pr_ids) == 4:
            try:
                raise_pull_request(conn, merger, pr_titles, viable_pr_ids)
            except robodoge.BranchCollisionError as err:
                print(err.msg)
            viable_pr_ids = []
            time.sleep(60*60) # Give the server a break

merger.repo.checkout(merger.safe_branch)
