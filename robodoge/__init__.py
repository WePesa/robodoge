from io import BytesIO
import datetime
import json
import os.path
import psycopg2
import pygit2
import pycurl
import subprocess
import yaml
from flask import Flask

coordinator = Flask(__name__)

class Error(Exception):
    """Base class for exceptions in this module."""
    pass

class BranchCollisionError(Error):
    """ Error creating a branch because a branch with the same name already exists """
    def __init__(self, msg):
        self.msg = msg
    def __str__(self):
        return repr(self.msg)

class BuildError(Error):
    """Base class for build errors in this module."""
    pass

class BuildMakeError(BuildError):
    """Build error while actually compiling """
    def __init__(self, cause):
        self.cause = cause

class BuildSetupError(BuildError):
    """Build error while configuring the build"""
    def __init__(self, cause):
        self.cause = cause

class BuildTestError(BuildError):
    """Build error in unit test execution"""
    def __init__(self, cause):
        self.cause = cause

class ConfigurationError(Error):
    def __init__(self, msg):
        self.msg = msg
    def __str__(self):
        return repr(self.msg)

class Robodoge:
    def __init__(self, config):
        if not 'dogecoin_repo' in config:
            raise ConfigurationError('Missing "dogecoin_repo" section from configuration')
        if not 'committer' in config['dogecoin_repo']:
            raise ConfigurationError('Missing "committer" section in "dogecoin_repo" section of configuration')
        if not 'branch' in config['dogecoin_repo']:
            raise ConfigurationError('Missing "branch" value in "dogecoin_repo" section of configuration')
        if not 'path' in config['dogecoin_repo']:
            raise ConfigurationError('Missing "path" value in "dogecoin_repo" section of configuration')

        if not 'github' in config:
            raise ConfigurationError('Missing "github" section from configuration')
        if not 'private_token' in config['github']:
            raise ConfigurationError('Missing "private_token" section in "github" section of configuration')

        if not 'http_auth' in config:
            raise ConfigurationError('Missing "http_auth" section from configuration')

        self.repo = pygit2.Repository(config['dogecoin_repo']['path'] + os.path.sep + '.git')
        self.config = config
        self.base_branch = self.repo.lookup_branch(config['dogecoin_repo']['branch'], pygit2.GIT_BRANCH_REMOTE)
        if not self.base_branch:
            raise ConfigurationError('Could not find upstream branch %s' % config['dogecoin_repo']['branch'])

        self.committer = pygit2.Signature(config['dogecoin_repo']['committer']['name'], config['dogecoin_repo']['committer']['email'])
        self.git_username = 'rnicoll' # FIXME: Don't hardcode
        self.private_token = config['github']['private_token']
        self.safe_branch = self.repo.lookup_branch('1.9-dev', pygit2.GIT_BRANCH_LOCAL) # FIXME: Don't hardcode

    def apply_pull_requests(self, conn, head_branch, pr_ids):
        """
        Apply one or more pull requests to a branch.
        """
        head_branch_oid = None
        for entry in self.repo.lookup_reference('refs/heads/' + head_branch.branch_name).log():
            head_branch_oid = entry.oid_new
            break
        parent_oid = head_branch_oid
        for pr_id in pr_ids:
            # Apply commits to PR
            for commit_oid in get_commit_oids(conn, pr_id):
                commit = self.repo.get(commit_oid)
                self.repo.cherrypick(commit_oid)
                if self.repo.index.conflicts:
                    self.repo.reset(head_branch_oid, pygit2.GIT_RESET_HARD)
                    return False
                if parent_oid:
                    prev_commit = self.repo.get(parent_oid)
                    parents = [parent_oid]
                else:
                    parents = []

                parent_oid = self.repo.create_commit(
                    'refs/heads/' + head_branch.branch_name,
                    commit.author, self.committer, commit.message,
                    self.repo.index.write_tree(),
                    parents
                )
                self.repo.lookup_reference('CHERRY_PICK_HEAD').delete()
        return True

    def build_pr_request(self, title, body, head_branch_name):
        """
        Raise a pull request against the given GitHub repository
        """
        return {
            'title': title,
            'body': body,
            'head': self.git_username + ":" + head_branch_name,
            'base': self.base_branch.branch_name.split('/')[1]
        }

    def call_github(self, url, request, method=None):
        """
        Raise a pull request against the given GitHub repository
        """

        buffer = BytesIO()
        c = pycurl.Curl()
        c.setopt(c.URL, url)
        c.setopt(c.POSTFIELDS, json.dumps(request))
        c.setopt(c.HTTPHEADER, ["Content-Type: application/json; charset=utf-8"])
        c.setopt(c.USERNAME, self.private_token)
        c.setopt(c.PASSWORD, 'x-oauth-basic')
        c.setopt(c.WRITEDATA, buffer)
        if method:
            c.setopt(c.CUSTOMREQUEST, method)
        else:
            c.setopt(c.POST, 1)
        c.perform()
        status_code = c.getinfo(c.RESPONSE_CODE)
        c.close()

        if status_code < 200 or status_code> 299:
            raise Error("Returned status from GitHub API was %d, expected 200-range status code" % status_code)
        return json.loads(buffer.getvalue().decode('UTF-8'))

    def create_branch(self, branch_name):
        branch = self.repo.lookup_branch(branch_name, pygit2.GIT_BRANCH_LOCAL)
        if not branch:
            base_branch_ref = self.repo.lookup_reference('refs/remotes/' + self.base_branch.branch_name)
            self.repo.create_branch(branch_name, base_branch_ref.get_object(), False)
            branch = self.repo.lookup_branch(branch_name, pygit2.GIT_BRANCH_LOCAL)
            return branch
        else:
            raise BranchCollisionError('Branch %s already exists, aborting' % branch_name)

    def get_connection(self):
        if 'pgsql' not in self.config:
            raise ConfigurationError("Expected 'pgsql' section in configuration.")
        
        pgsql_config = self.config['pgsql']
        if 'db' not in pgsql_config:
            raise Exception("Expected PostgreSQL database name to be provided in configuration file.")
        if 'username' not in pgsql_config:
            raise Exception("Expected PostgreSQL username to be provided in configuration file.")
        if 'password' not in pgsql_config:
            raise Exception("Expected PostgreSQL password to be provided in configuration file.")

        return psycopg2.connect("host=localhost dbname=%(db)s user=%(username)s password=%(password)s port=%(port)s" % pgsql_config)

    def raise_pr(self, repo_name, title, body, head_branch_name):
        request = self.build_pr_request(title, body, head_branch_name)
        url = 'https://api.github.com/repos/%s/pulls' % repo_name
        return self.call_github(url, request)

def compile_dogecoin(path):
    """
    Compile the Dogecoin client found at the given path, and then run its unit tests.
    
    Raises BuildError subclasses in case of problems.
    """

    original_path = os.getcwd()
    os.chdir(path)
    try:
        try:
            subprocess.check_output([path + os.path.sep + 'autogen.sh'])
            subprocess.check_output([path + os.path.sep + 'configure'])
        except subprocess.CalledProcessError as err:
            raise BuildSetupError(err)
        try:
            subprocess.check_output(['make', 'clean'], stderr=subprocess.STDOUT)
            subprocess.check_output(['make'], stderr=subprocess.STDOUT)
        except subprocess.CalledProcessError as err:
            raise BuildMakeError(err)
        try:
            subprocess.check_output(['make', 'check'], stderr=subprocess.STDOUT)
        except subprocess.CalledProcessError as err:
            raise BuildTestError(err)
    finally:
        os.chdir(original_path)

def get_commit_oids(conn, pr_id):
    """ Retrieve the commit OIDs for the given pull request """
    commit_oids = []
    cursor = conn.cursor()
    try:
        cursor.execute(
        """SELECT commit.sha
            FROM pull_request pr
                JOIN pull_request_commit commit ON commit.pr_id=pr.id
            WHERE pr.id=%(pr_id)s 
                AND commit.to_merge='t'
                AND commit.merged='f'
            ORDER BY commit.ordinality ASC
        """, {'pr_id': pr_id})
        for record in cursor:
            commit_oids.append(pygit2.Oid(hex=record[0]))
    finally:
        cursor.close()
    return commit_oids

def load_configuration(filename):
  if not os.path.isfile(filename):
    raise ConfigurationError("Expected configuration file '" + filename + "'")

  with open(filename, 'r') as f:
    raw_config = f.read(10 * 1024 * 1024) # If you have a config over 10M in size, I give up

  try:
    config = yaml.load(raw_config)
  except yaml.parser.ParserError as e:
    raise ConfigurationError("Could not parse configuration file: {0}".format(e))

  return config

def extract_pr_data(pr, project):
    """ Extract data from a pull request for insertion/update into the database """
    data = {
       'id': pr['id'],
       'number': pr['number'],
       'project': project,
       'url': pr['url'],
       'html_url': pr['html_url'],
       'state': pr['state'],
       'title': pr['title'],
       'body': pr['body'].replace("\r\n", "\n"),
       'merge_commit_sha': pr['merge_commit_sha'],
       'base_ref': pr['base']['ref'],
       'created_at': datetime.datetime.strptime(pr['created_at'], '%Y-%m-%dT%H:%M:%SZ'),
    }
    if pr['assignee']:
        data['assignee_login'] = pr['assignee']['login']
    else:
        data['assignee_login'] = None
    if pr['milestone']:
        data['milestone_title'] = pr['milestone']['title']
    else:
        data['milestone_title'] = None
    if pr['merged_at']:
        data['merged_at'] = datetime.datetime.strptime(pr['merged_at'], '%Y-%m-%dT%H:%M:%SZ')
    else:
        data['merged_at'] = None
    if pr['user']:
        data['user_login'] = pr['user']['login']
    else:
        data['user_login'] = None

    return data

def insert_pr(cursor, pr, project):
    """ Insert a pull request into the database """
    data = extract_pr_data(pr, project)
    cursor.execute("""INSERT INTO pull_request
         (id, number, project, url, html_url, state, title, user_login, assignee_login, milestone_title, base_ref, body, created_at, merged_at, merge_commit_sha)
         VALUES (%(id)s, %(number)s, %(project)s, %(url)s, %(html_url)s, %(state)s, %(title)s, %(user_login)s, %(assignee_login)s, %(milestone_title)s, %(base_ref)s, %(body)s, %(created_at)s, %(merged_at)s, %(merge_commit_sha)s);""", data)

def update_pr(cursor, pr, project):
    """ Update a pull request which already exists in the database """
    data = extract_pr_data(pr, project)
    cursor.execute("""UPDATE pull_request
         SET number=%(number)s, state=%(state)s, title=%(title)s, assignee_login=%(assignee_login)s, milestone_title=%(milestone_title)s, merged_at=%(merged_at)s, merge_commit_sha=%(merge_commit_sha)s
         WHERE id=%(id)s""", data)
