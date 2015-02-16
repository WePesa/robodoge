#!/usr/bin/python3

import os
import pygit2
import subprocess
import sys
import time
import auto_merge

# Script to mass evaluate remaining pull requests, and raise them against Dogecoin
# where feasible.

def raise_pull_request(repo, conn, base_branch, committer, git_username, private_token, pr_titles, pr_ids):
    title = '[Auto] Bitcoin PR batch %s' % time.asctime()
    contents = []
    for pr_id in pr_ids:
        contents.append(pr_titles[pr_id])
    body = "Contains:\n\n* " + "\n* ".join(contents)

    # Create new branch
    batch_branch = auto_merge.create_branch(repo, base_branch, 'bitcoin-batch-%d' % int(time.time()))
    repo.checkout(batch_branch)
    auto_merge.apply_pull_requests(repo, conn, base_branch, batch_branch, committer, pr_ids)

    # Push branch upstream and raise PR
    branch_ref = repo.lookup_reference('refs/heads/' + batch_branch.branch_name)

    print('Pushing branch %s to origin' % batch_branch.branch_name)
    remote = repo.remotes["origin"]
    remote.credentials = pygit2.UserPass(private_token, 'x-oauth-basic')
    remote.push([branch_ref.name])

    # Raise a PR from the new branch
    head = '%s:%s' % (git_username, batch_branch.branch_name)
    base = base_branch.branch_name.split('/')[1]
    new_pr = auto_merge.raise_pr('dogecoin/dogecoin', title, body, head, base, private_token)

    cursor = conn.cursor()
    try:
        # Mark component PRs done
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
                'body': new_pr['body']
            }
        )

        for pr_id in viable_pr_ids:
            cursor.execute("UPDATE pull_request_commit SET merged='t', raised_pr_id=%(raised_pr)s WHERE pr_id=%(pr_id)s", {
                'pr_id': pr_id,
                'raised_pr': new_pr['id']
            })
        conn.commit()
    finally:
        cursor.close()

def test_pr_merge(conn, path, repo, pr_id, safe_branch, base_branch, committer):
    """
    Test if a pull request can be cleanly merged against the current development branch. Returns true/false
    """

    # Test if the branch exists already, create it if not
    head_branch = auto_merge.create_branch(repo, base_branch, 'bitcoin-pr-%d' % pr_id)
    if not head_branch:
        return False
    try:
        repo.checkout(head_branch)

        if not auto_merge.apply_pull_requests(repo, conn, base_branch, head_branch, committer, [pr_id]):
            return False

        # Make sure it's a viable build too
        print('Attempting compilation of PR %d' % pr_id)
        try:
            auto_merge.compile_dogecoin(path)
        except subprocess.CalledProcessError:
            return False
    finally:
        repo.checkout(safe_branch)
        repo.lookup_branch(head_branch.branch_name, pygit2.GIT_BRANCH_LOCAL).delete()

    return True

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
repo = pygit2.Repository(config['dogecoin_repo']['path'] + os.path.sep + '.git')
base_branch = repo.lookup_branch(config['dogecoin_repo']['branch'], pygit2.GIT_BRANCH_REMOTE)

if not base_branch:
    print('Could not find upstream branch %s' % config['dogecoin_repo']['branch'])
    sys.exit(1)

# Pull Github authentication details from configuration

if not 'github' in config:
    print('Missing "github" section from configuration')
    sys.exit(1)
if not 'private_token' in config['github']:
    print('Missing "private_token" section in "github" section of configuration')
    sys.exit(1)

git_username = 'rnicoll' # FIXME: Don't hardcode
private_token = config['github']['private_token']
safe_branch = repo.lookup_branch('1.9-dev', pygit2.GIT_BRANCH_LOCAL) # FIXME: Don't hardcode

conn = auto_merge.get_connection(config)
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
        if test_pr_merge(conn, config['dogecoin_repo']['path'], repo, pr_id, safe_branch, base_branch, committer):
            viable_pr_ids.append(pr_id)
        if len(viable_pr_ids) == 4:
            raise_pull_request(repo, conn, base_branch, committer, git_username, private_token, pr_titles, viable_pr_ids)
            viable_pr_ids = []
            time.sleep(60*60) # Give the server a break

    if len(viable_pr_ids) > 0:
        raise_pull_request(repo, conn, base_branch, committer, git_username, private_token, pr_titles, viable_pr_ids)
finally:
    conn.close()

repo.checkout(safe_branch)
