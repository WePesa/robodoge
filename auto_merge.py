from io import BytesIO
import json
import os.path
import psycopg2
import pygit2
import pycurl
import subprocess
import yaml

class ConfigurationException(Exception):
  def __init__(self, value):
    self.value = value
  def __str__(self):
    return repr(self.value)

def apply_pull_requests(repo, conn, base_branch, branch, committer, pr_ids):
    branch_oid = None
    for entry in repo.lookup_reference('refs/heads/' + branch.branch_name).log():
        branch_oid = entry.oid_new
        break
    parent_oid = branch_oid
    for pr_id in pr_ids:
        # Apply commits to PR
        for commit_oid in get_commit_oids(conn, pr_id):
            commit = repo.get(commit_oid)
            repo.cherrypick(commit_oid)
            if repo.index.conflicts:
                repo.reset(branch_oid, pygit2.GIT_RESET_HARD)
                return False
            if parent_oid:
                prev_commit = repo.get(parent_oid)
                parents = [parent_oid]
            else:
                parents = []

            parent_oid = repo.create_commit(
                'refs/heads/' + branch.branch_name,
                commit.author, committer, commit.message,
                repo.index.write_tree(),
                parents
            )
            repo.lookup_reference('CHERRY_PICK_HEAD').delete()
    return True

def compile_dogecoin(path):
    original_path = os.getcwd()
    os.chdir(path)
    try:
        subprocess.check_output([path + os.path.sep + 'autogen.sh'])
        subprocess.check_output([path + os.path.sep + 'configure'])
        subprocess.check_output(['make', 'clean'], stderr=subprocess.STDOUT)
        subprocess.check_output(['make'], stderr=subprocess.STDOUT)
        subprocess.check_output(['make', 'check'], stderr=subprocess.STDOUT)
    finally:
        os.chdir(original_path)

def create_branch(repo, base_branch, branch_name):
    branch = repo.lookup_branch(branch_name, pygit2.GIT_BRANCH_LOCAL)
    if not branch:
        base_branch_ref = repo.lookup_reference('refs/remotes/' + base_branch.branch_name)
        repo.create_branch(branch_name, base_branch_ref.get_object(), False)
        branch = repo.lookup_branch(branch_name, pygit2.GIT_BRANCH_LOCAL)
        return branch
    else:
        print('Branch %s already exists, aborting' % branch_name)
        return None

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

def raise_pr(repo_name, title, body, head, base, private_token):
    """
    Raise a pull request against the given GitHub repository
    """
    request = {
        'title': title,
        'body': body,
        'head': head,
        'base': base
    }

    buffer = BytesIO()
    c = pycurl.Curl()
    c.setopt(c.URL, 'https://api.github.com/repos/%s/pulls' % repo_name)
    c.setopt(c.POST, 1)
    c.setopt(c.POSTFIELDS, json.dumps(request))
    c.setopt(c.HTTPHEADER, ["Content-Type: application/json; charset=utf-8"])
    c.setopt(c.USERNAME, private_token)
    c.setopt(c.PASSWORD, 'x-oauth-basic')
    c.setopt(c.WRITEDATA, buffer)
    c.perform()
    status_code = c.getinfo(c.RESPONSE_CODE)
    c.close()

    if status_code != 201:
        print(buffer.getvalue().decode('UTF-8'))
        raise Exception("Returned status from GitHub API was %d, expected 201 (Created)" % status_code)
    return json.loads(buffer.getvalue().decode('UTF-8'))

def load_configuration(filename):
  if not os.path.isfile(filename):
    raise ConfigurationException("Expected configuration file '" + filename + "'")

  with open(filename, 'r') as f:
    raw_config = f.read(10 * 1024 * 1024) # If you have a config over 10M in size, I give up

  try:
    config = yaml.load(raw_config)
  except yaml.parser.ParserError as e:
    raise ConfigurationException("Could not parse configuration file: {0}".format(e))

  return config

def get_connection(config):
  if 'pgsql' not in config:
    raise ConfigurationException("Expected 'pgsql' section in configuration file '" + config_filename + "'")
  
  pgsql_config = config['pgsql']
  if 'db' not in pgsql_config:
    raise Exception("Expected PostgreSQL database name to be provided in configuration file")
  if 'username' not in pgsql_config:
    raise Exception("Expected PostgreSQL username to be provided in configuration file")
  if 'password' not in pgsql_config:
    raise Exception("Expected PostgreSQL password to be provided in configuration file")

  return psycopg2.connect("host=localhost dbname=%(db)s user=%(username)s password=%(password)s" % pgsql_config)
