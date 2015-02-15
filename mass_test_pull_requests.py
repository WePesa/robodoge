#!/usr/bin/python3

import sys
import auto_merge
import pygit2
import time

# Script to mass evaluate remaining pull requests, and raise them against Dogecoin
# where feasible.

def create_branch(repo, base_branch, branch_name):
    branch = repo.lookup_branch(branch_name, pygit2.GIT_BRANCH_LOCAL)
    if not branch:
        print('Creating new branch %s' % branch_name)
        base_branch_ref = repo.lookup_reference('refs/remotes/' + base_branch.branch_name)
        repo.create_branch(branch_name, base_branch_ref.get_object(), False)
        branch = repo.lookup_branch(branch_name, pygit2.GIT_BRANCH_LOCAL)
        return branch
    else:
        print('Branch %s already exists, aborting' % branch_name)
        return None
    

def attempt_merge_pr(conn, repo, pr_id, base_branch, committer, git_username, git_password):
    title = None
    body = None
    merged_commits = []
    
    # Test if the branch exists already, create it if not
    branch = create_branch(repo, base_branch, 'bitcoin-pr-%d' % pr_id)
    if not branch:
        print('Branch %s already exists, aborting' % branch_name)
        return False

    repo.checkout(branch)

    # Find the OID of the HEAD commit on the branch for committing against
    branch_ref = repo.lookup_reference('refs/heads/' + branch.branch_name)
    branch_oid = None
    for entry in branch_ref.log():
        branch_oid = entry.oid_new
        break
    parent_oid = branch_oid

    cursor = conn.cursor()
    try:
        cursor.execute(
            """SELECT pr.title, pr.body, commit.sha
                FROM pull_request pr
                    JOIN pull_request_commit commit ON commit.pr_id=pr.id
                WHERE pr.id=%(pr_id)s 
                    AND commit.to_merge='t'
                    AND commit.merged='f'
                ORDER BY commit.ordinality ASC
        """, {'pr_id': pr_id})
        for record in cursor:
            if not title:
                title = record[0]
                body = record[1]

            commit_oid = pygit2.Oid(hex=record[2])
            print('Cherrypicking commit %s' % commit_oid)
            repo.cherrypick(commit_oid)
            if repo.index.conflicts:
                print('Commit %s cannot be applied cleanly. Reverting to %s' % (commit_oid, branch_oid))
                repo.reset(branch_oid, pygit2.GIT_RESET_HARD)
                repo.checkout(repo.lookup_branch('refs/heads/1.9-dev')) # TODO: Don't hardcode safe branch
                branch.delete()
                return None
            else:
                # TODO: Use previous cherrypick as base, not just the branch
                parent_oid = commit_cherrypick(repo, branch, repo.get(commit_oid), committer, parent_oid)
                cherrypick_ref = repo.lookup_reference('CHERRY_PICK_HEAD')
                cherrypick_ref.delete()

        print('Pushing branch %s to origin' % branch.branch_name)
        remote = repo.remotes["origin"]
        remote.credentials = pygit2.UserPass(git_username, git_password)
        remote.push([branch_ref.name])

        repo.checkout(repo.lookup_branch('refs/heads/1.9-dev')) # TODO: Don't hardcode safe branch
        branch.delete()

        head = '%s:%s' % (git_username, branch_name)
        print('Raising new pull request')
        new_pr = raise_pr('dogecoin/dogecoin', title, body, head, branch.branch_name, git_username, git_password)

        cursor.execute("UPDATE pull_request_commit SET merged='t' WHERE pr_id=%(pr_id)s", {'pr_id': pr_id})
        # TODO: Note the new PR ID
        conn.commit()
    finally:
        cursor.close()

    print('Raised new PR %s' % new_pr['html_url'])

    return new_pr

config = auto_merge.load_configuration('config.yml')

# Load the repository and the branch to work from
if not 'dogecoin_repo' in config:
    print('Missing "dogecoin_repo" section from configuration')
    sys.exit(1)
if not 'committer' in config['dogecoin_repo']:
    print('Missing "committer" section in "dogecoin_repo" section of configuration')
    sys.exit(1)
if not 'branch' in config['dogecoin_repo']:
    print('Missing "branch" value in "dogecoin_repo" section of configuration')
    sys.exit(1)
if not 'path' in config['dogecoin_repo']:
    print('Missing "path" value in "dogecoin_repo" section of configuration')
    sys.exit(1)

committer = pygit2.Signature(config['dogecoin_repo']['committer']['name'], config['dogecoin_repo']['committer']['email'])
repo = pygit2.Repository(config['dogecoin_repo']['path'])
head_branch = repo.lookup_branch(config['dogecoin_repo']['branch'], pygit2.GIT_BRANCH_REMOTE)

if not head_branch:
    print('Could not find upstream branch %s' % config['dogecoin_repo']['branch'])
    sys.exit(1)

# Pull Github authentication details from configuration

if not 'github' in config:
    print('Missing "github" section from configuration')
    sys.exit(1)
if not 'private_token' in config['github']:
    print('Missing "private_token" section in "github" section of configuration')
    sys.exit(1)

git_username = config['github']['private_token']
git_password = 'x-oauth-basic'

conn = auto_merge.get_connection(config)
try:
    cursor = conn.cursor()
    try:
        # Find pull requests to evaluate
        cursor.execute(
            """SELECT DISTINCT pr.id 
                FROM pull_request pr
                    JOIN pull_request_commit commit ON commit.pr_id=pr.id
                WHERE commit.to_merge='t' AND commit.merged='f'""")
        for record in cursor:
            attempt_merge_pr(conn, repo, record[0], head_branch, committer, git_username, git_password)
            break
    finally:
        cursor.close()
finally:
    conn.close()
