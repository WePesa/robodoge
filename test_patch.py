#!/usr/bin/python3

import re
import os
import string
import sys
import auto_merge
import pygit2
import time

def attempt_cherrypick_push(repo, base_branch, commit_oid, remote):
    # Test if the branch exists already, create it if not
    branch = repo.lookup_branch('1.9-' + str(commit_oid), pygit2.GIT_BRANCH_LOCAL)
    if not branch:
        print('Creating new branch')
        base_branch = repo.lookup_branch('upstream/1.9-dev', pygit2.GIT_BRANCH_REMOTE)
        base_branch_ref = repo.lookup_reference('refs/remotes/' + base_branch.branch_name)
        repo.create_branch('1.9-' + str(commit_oid), base_branch_ref.get_object(), False)
        branch = repo.lookup_branch('1.9-' + commit_id, pygit2.GIT_BRANCH_LOCAL)
        repo.checkout(branch)
    else:
        print('Branch already exists, aborting')
        return False

    # Find the OID of the HEAD commit on the branch
    branch_ref = repo.lookup_reference('refs/heads/' + branch.branch_name)
    branch_oid = None
    for entry in branch_ref.log():
        branch_oid = entry.oid_new
        break

    print('Merging commit ' + str(commit_oid))
    repo.cherrypick(commit_oid)

    if repo.index.conflicts:
        print('Commit cannot be applied cleanly. Reverting to ' + str(branch_oid))
        repo.reset(branch_oid, pygit2.GIT_RESET_HARD)
        repo.checkout(repo.lookup_branch('refs/heads/1.9-dev'))
        branch.delete()
        return False
    else:
        print('Commit applied cleanly, pushing to origin')
        commit_cherrypick(repo, branch, repo.get(commit_oid), committer)
        cherrypick_ref = repo.lookup_reference('CHERRY_PICK_HEAD')
        cherrypick_ref.delete()
        remote.push([branch_ref.name])
        return True

def commit_cherrypick(repo, branch, commit, committer):
    tree = repo.TreeBuilder(commit.tree).write()
    parent_oid = None
    branch_ref = repo.lookup_reference('refs/heads/' + branch.branch_name)
    for entry in branch_ref.log():
        parent_oid = entry.oid_new
        break

    if parent_oid:
        prev_commit = repo.get(parent_oid)
        parents = [parent_oid]
    else:
        parents = []

    repo.create_commit(
        'refs/heads/' + branch.branch_name,
        commit.author, committer, commit.message,
        repo.index.write_tree(),
        parents
    )

if len(sys.argv) < 2:
    print('Expected commit ID as sole parameter.')
    sys.exit(1)

commit_id = sys.argv[1].strip()
if len(commit_id) != 40:
    print('Commit ID ' + commit_id + ' is invalid, expected 40 characters, found ' + str(len(commit_id)) + '.')
    sys.exit(1)

commit_oid = pygit2.Oid(hex=commit_id)
config = auto_merge.load_configuration('config.yml')
committer = pygit2.Signature(config['dogecoin_repo']['committer']['name'], config['dogecoin_repo']['committer']['email'])
repo = pygit2.Repository(config['dogecoin_repo']['path'])
git_username = config['dogecoin_repo']['committer']['username']
git_password = input('Password for Git account "' + git_username + '": ')

# Fetch the commit from Bitcoin Core if needed
if repo.get(commit_oid):
    print('Commit already ready to merge')
else:
    print("Fetching Bitcoin repo updates")
    tp = repo.remotes["bitcoin"].fetch(None, None)
    while tp.received_objects<tp.total_objects:
        print(str(tp.received_objects / tp.total_objects * 100.0) + '%')
        time.sleep(1)

one_nine_branch = repo.lookup_branch('upstream/1.9-dev', pygit2.GIT_BRANCH_REMOTE)
remote = repo.remotes["origin"]
remote.credentials = pygit2.UserPass(git_username, git_password)

attempt_cherrypick_push(repo, one_nine_branch, commit_oid, remote)

# TODO: Compile
# TODO: Run unit tests
# TODO: Run full sync
# TODO: Generate PR
