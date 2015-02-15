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
    

def attempt_merge_pr(conn, repo, pr_id, base_branch, committer, git_username, private_token):
    title = None
    body = None
    merged_commits = []
    
    # Test if the branch exists already, create it if not
    branch = create_branch(repo, base_branch, 'bitcoin-pr-%d' % pr_id)
    if not branch:
        return False

    repo.checkout(branch)

    # Find the OID of the HEAD commit on the branch for committing against
    branch_ref = repo.lookup_reference('refs/heads/' + branch.branch_name)
    branch_oid = None
    for entry in branch_ref.log():
        branch_oid = entry.oid_new
        break
    parent_oid = branch_oid

    safe_branch = repo.lookup_branch('1.9-dev', pygit2.GIT_BRANCH_LOCAL) # TODO: Don't hardcode safe branch

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
                repo.checkout(safe_branch)
                branch.delete()
                return None
            else:
                parent_oid = auto_merge.commit_cherrypick(repo, branch, repo.get(commit_oid), committer, parent_oid)
                cherrypick_ref = repo.lookup_reference('CHERRY_PICK_HEAD')
                cherrypick_ref.delete()

        print('Pushing branch %s to origin' % branch.branch_name)
        remote = repo.remotes["origin"]
        remote.credentials = pygit2.UserPass(private_token, 'x-oauth-basic')
        remote.push([branch_ref.name])

        repo.checkout(safe_branch)

        head = '%s:%s' % (git_username, branch.branch_name) # TODO: Don't hard-code my username
        base = base_branch.branch_name.split('/')[1]
        print('Raising new pull request')
        new_pr = auto_merge.raise_pr('dogecoin/dogecoin', '[Auto] ' + title, body, head, base, private_token)

        cursor.execute(
            """INSERT INTO pull_request (id, project, url, html_url, state, title, user_login, body, created_at) 
                 VALUES (%(id)s, 'dogecoin', %(url)s, %(html_url)s, %(state)s, %(title)s, %(user_login)s, %(body)s, NOW())""",
            {
                'id': new_pr['id'],
                'url': new_pr['url'],
                'html_url': new_pr['html_url'],
                'state': new_pr['state'],
                'title': new_pr['title'],
                'user_login': git_username,
                'body': body
	    }
        )
        cursor.execute("UPDATE pull_request_commit SET merged='t', raised_pr_id=%(raised_pr)s WHERE pr_id=%(pr_id)s", {
            'pr_id': pr_id,
            'raised_pr': new_pr['id']
        })
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

git_username = 'rnicoll' # TODO: Don't hardcode
private_token = config['github']['private_token']

conn = auto_merge.get_connection(config)
try:
    cursor = conn.cursor()
    count = 0
    try:
        # Find pull requests to evaluate
        cursor.execute(
            """SELECT pr.id
                FROM pull_request pr
                    JOIN pull_request_commit commit ON commit.pr_id=pr.id
                WHERE commit.to_merge='t' AND commit.merged='f'
                ORDER BY pr.merged_at, pr.id ASC""")
        last_pr = None
        for record in cursor:
            pr_id = record[0]
            if last_pr == pr_id:
                 # We filter after extraction as PostgreSQL doesn't like mixing DISTINCT and ORDER BY
                 continue
            last_pr = pr_id
            if attempt_merge_pr(conn, repo, pr_id, head_branch, committer, git_username, private_token):
                count += 1
                if count > 1:
                    break
    finally:
        cursor.close()
finally:
    conn.close()
