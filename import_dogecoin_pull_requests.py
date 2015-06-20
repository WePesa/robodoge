#!/usr/bin/python3
import psycopg2
import pycurl
import json
from io import BytesIO
import robodoge
import datetime
import time

def import_pull_requests(merger, conn, page, private_token):
    buffer = BytesIO()
    c = pycurl.Curl()
    c.setopt(c.URL, 'https://api.github.com/repos/dogecoin/dogecoin/pulls?state=open&page=%d' % page)
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
    print('Fetched %d pull requests from https://api.github.com/repos/dogecoin/dogecoin/pulls?state=open&page=%d' % (len(response), page))
    if len(response) == 0:
        # No more data
        return False

    cursor = conn.cursor()
    try:
        for pr in response:
            write_pr(merger, cursor, pr, private_token)
            conn.commit()
    finally:
        cursor.close()

    return True

def import_commits(merger, cursor, pr_id, commits_url, private_token):
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
        write_commit(merger, cursor, pr_id, ordinality, commit)
        ordinality += 1

def write_commit(merger, cursor, pr_id, ordinality, commit):
    cursor.execute(
     """INSERT INTO pull_request_commit (pr_id, ordinality, sha)
         VALUES (%(pr_id)s, %(ordinality)s, %(sha)s);""",
     {
       'pr_id': pr_id,
       'ordinality': ordinality,
       'sha': commit['sha']
     })

def write_pr(merger, cursor, pr, private_token):
    """ Write a pull request and its commits into the database """
    # Check record doesn't exist before trying to insert
    cursor.execute("SELECT id FROM pull_request WHERE id=%(id)s", {'id': pr['id']})
    if cursor.fetchone():
       robodoge.update_pr(cursor, pr, 'dogecoin/dogecoin')
    else:
       robodoge.insert_pr(cursor, pr, 'dogecoin/dogecoin')
       import_commits(merger, cursor, pr['id'], pr['commits_url'], private_token)

    time.sleep(1) # Badly rate limit requests

config = robodoge.load_configuration('config.yml')
try:
    merger = robodoge.Robodoge(config)
except robodoge.ConfigurationError as err:
    print(err.msg)
    sys.exit(1)
github_config = config['github']
if not 'private_token' in github_config:
    print('Expected "private_token" in Github section of configuration')
    sys.exit(1)

conn = merger.get_connection()
try:
    page = 1
    while import_pull_requests(merger, conn, page, github_config['private_token']):
        page += 1
finally:
    conn.close()
