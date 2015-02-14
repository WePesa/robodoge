import psycopg2
import pycurl
import json
from io import BytesIO
import auto_merge
import datetime
import time

def import_pull_requests(conn, page, private_token):
    buffer = BytesIO()
    c = pycurl.Curl()
    c.setopt(c.URL, 'https://api.github.com/repos/bitcoin/bitcoin/pulls?state=closed&page=%d' % page)
    c.setopt(c.USERNAME, private_token)
    c.setopt(c.PASSWORD, 'x-oauth-basic')
    c.setopt(c.WRITEDATA, buffer)
    c.perform()
    status_code = c.getinfo(c.RESPONSE_CODE)
    c.close()

    if status_code != 200:
        raise Exception('Received non-200 response from remote server')
    # TODO: Handle rate limiting without throwing an exception

    response = json.loads(buffer.getvalue().decode('UTF-8'))
    print('Fetched %d pull requests' % len(response))
    if len(response) == 0:
        # No more data
        return False

    cursor = conn.cursor()
    try:
        for pr in response:
            write_pr(cursor, pr, private_token)
            conn.commit()
            time.sleep(1) # Badly rate limit requests
    finally:
        cursor.close()

    return True

def import_commits(cursor, pr_id, commits_url, private_token):
    buffer = BytesIO()
    c = pycurl.Curl()
    c.setopt(c.URL, commits_url)
    c.setopt(c.USERNAME, private_token)
    c.setopt(c.PASSWORD, 'x-oauth-basic')
    c.setopt(c.WRITEDATA, buffer)
    c.perform()
    status_code = c.getinfo(c.RESPONSE_CODE)
    c.close()

    if status_code != 200:
        raise Exception('Received non-200 response from remote server')

    response = json.loads(buffer.getvalue().decode('UTF-8'))
    ordinality = 1
    for commit in response:
        write_commit(cursor, pr_id, ordinality, commit)
        ordinality += 1

def write_commit(cursor, pr_id, ordinality, commit):
    cursor.execute(
     """INSERT INTO pull_request_commit (pr_id, ordinality, sha)
         VALUES (%(pr_id)s, %(ordinality)s, %(sha)s);""",
     {
       'pr_id': pr_id,
       'ordinality': ordinality,
       'sha': commit['sha']
     })

def write_pr(cursor, pr, private_token):
    """ Write a pull request and its commits into the database """
    # Check record doesn't exist before trying to insert
    cursor.execute("SELECT id FROM pull_request WHERE id=%(id)s", {'id': pr['id']})
    if cursor.fetchone():
       print('Pull request %s already imported, skipping' % pr['id'])
       return False

    data = {
       'id': pr['id'],
       'project': "bitcoin/bitcoin",
       'url': pr['url'],
       'state': pr['state'],
       'title': pr['title'],
       'user_login': pr['user']['login'],
       'body': pr['body'].replace("\r\n", "\n"),
       'merge_commit_sha': pr['merge_commit_sha'],
       'created_at': datetime.datetime.strptime(pr['created_at'], '%Y-%m-%dT%H:%M:%SZ')
    }
    if pr['merged_at']:
        data['merged_at'] = datetime.datetime.strptime(pr['merged_at'], '%Y-%m-%dT%H:%M:%SZ')
    else:
        data['merged_at'] = None
    cursor.execute("""INSERT INTO pull_request (id, project, url, state, title, user_login, body, created_at, merged_at, merge_commit_sha)
         VALUES (%(id)s, %(project)s, %(url)s, %(state)s, %(title)s, %(user_login)s, %(body)s, %(created_at)s, %(merged_at)s, %(merge_commit_sha)s);""", data)

    import_commits(cursor, pr['id'], pr['commits_url'], private_token)
    return True

config = auto_merge.load_configuration('config.yml')
if not 'github' in config:
    print('Expected "github" section in configuration')
    sys.exit(1)
github_config = config['github']
if not 'private_token' in github_config:
    print('Expected "private_token" in Github section of configuration')
    sys.exit(1)

conn = auto_merge.get_connection(config)
try:
    page = 1
    while import_pull_requests(conn, page, github_config['private_token']):
        page += 1
finally:
    conn.close()
