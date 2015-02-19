#!/usr/bin/python3

import os
import pygit2
import subprocess
import sys
import time
import robodoge

# Script to mass evaluate remaining pull requests, and raise them against Dogecoin
# where feasible.

def build_pr_body(pr_titles, pr_ids):
    contents = []
    for pr_id in pr_ids:
        contents.append(pr_titles[pr_id])
    return "Contains:\n\n* " + "\n* ".join(contents)

def mark_commits_merged(conn, merger, new_pr, pr_ids):
    cursor = conn.cursor()
    try:
        # Mark the new PR to the database
        robodoge.write_pr(cursor, new_pr, 'dogecoin/dogecoin')

        # Mark component PRs done
        for pr_id in pr_ids:
            cursor.execute("UPDATE pull_request_commit SET merged='t', raised_pr_id=%(raised_pr)s WHERE pr_id=%(pr_id)s", {
                'pr_id': pr_id,
                'raised_pr': new_pr['id']
            })
        conn.commit()
    finally:
        cursor.close()

def raise_pull_request(conn, merger, pr_titles, pr_ids):
    repo = merger.repo
    title = '[Auto] Bitcoin PR batch %s' % time.asctime()
    body = build_pr_body(pr_titles, pr_ids)

    # Create new branch
    branch_name = 'bitcoin-batch-%d' % int(time.time())
    batch_branch = merger.create_branch(branch_name)
    repo.checkout(batch_branch)
    merger.apply_pull_requests(conn, batch_branch, pr_ids)

    # Push branch upstream and raise PR
    branch_ref = repo.lookup_reference('refs/heads/' + batch_branch.branch_name)

    print('Pushing branch %s to origin' % batch_branch.branch_name)
    remote = repo.remotes["origin"]
    remote.credentials = pygit2.UserPass(merger.private_token, 'x-oauth-basic')
    remote.push([branch_ref.name])

    # Raise a PR from the new branch
    new_pr = merger.raise_pr('dogecoin/dogecoin', title, body, batch_branch.branch_name)
    mark_commits_merged(conn, merger, new_pr, pr_ids)

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

config = robodoge.load_configuration('config.yml')
try:
    merger = robodoge.Robodoge(config)
except robodoge.ConfigurationError as err:
    print(err.msg)
    sys.exit(1)

conn = merger.get_connection()
try:
    pr_titles = {}
    ordered_pr_ids = []
    cursor = conn.cursor()
    try:
        # Find pull requests to evaluate
        cursor.execute(
            """SELECT pr.id, pr.title
                FROM pull_request pr
                    JOIN pull_request_commit commit ON commit.pr_id=pr.id
                WHERE commit.to_merge='t' AND commit.merged='f'
                ORDER BY pr.merged_at, pr.id ASC""")
        for record in cursor:
            pr_id = record[0]
            if pr_id not in ordered_pr_ids:
                ordered_pr_ids.append(pr_id)
                pr_titles[pr_id] = record[1]
    finally:
        cursor.close()

    viable_pr_ids = []
    for pr_id in ordered_pr_ids:
        if test_pr_merge(conn, merger, pr_id):
            viable_pr_ids.append(pr_id)
        if len(viable_pr_ids) == 4:
            try:
                raise_pull_request(conn, merger, pr_titles, viable_pr_ids)
            except robodoge.BranchCollisionError as err:
                print(err.msg)
            viable_pr_ids = []
            time.sleep(60*60) # Give the server a break

    if len(viable_pr_ids) > 0:
        try:
            raise_pull_request(conn, merger, pr_titles, viable_pr_ids)
        except robodoge.BranchCollisionError as err:
            print(err.msg)
finally:
    conn.close()

merger.repo.checkout(safe_branch)
