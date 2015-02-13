#!/usr/bin/python3

import string
import sys
import auto_merge
import pygit2
import pycurl
import json
from io import StringIO

if len(sys.argv) < 2:
    print('Expected commit ID as sole parameter.')
    sys.exit(1)

commit_id = sys.argv[1].strip()
if len(commit_id) != 40:
    print('Commit ID ' + commit_id + ' is invalid, expected 40 characters, found ' + str(len(commit_id)) + '.')
    sys.exit(1)

commit_oid = pygit2.Oid(hex=commit_id)
config = auto_merge.load_configuration('config.yml')
repo = pygit2.Repository(config['dogecoin_repo']['path'])
git_username = config['dogecoin_repo']['committer']['username']
git_password = input('Password for Git account "' + git_username + '": ')

commit = repo.get(commit_oid)
body = commit.message
body_lines = body.split('\n')
title = body_lines[0]

print(title)

request = {
    'title': title,
    'body': body,
    'head': git_username + ':1.9-' + str(commit_oid),
    'base': '1.9-dev'
}

buffer = StringIO()
c = pycurl.Curl()
c.setopt(c.URL, 'https://api.github.com/repos/dogecoin/dogecoin/pulls')
c.setopt(c.POST, 1)
c.setopt(c.POSTFIELDS, json.dumps(request))
c.setopt(c.HTTPHEADER, ["Content-Type: application/json; charset=utf-8"])
c.setopt(c.USERNAME, git_username)
c.setopt(c.PASSWORD, git_password)
c.setopt(c.WRITEDATA, buffer)
c.perform()
c.close()

response = json.load(buffer)
print('Status: %d' % c.getinfo(c.RESPONSE_CODE))
print('URL: %s' % response['html_url'])
