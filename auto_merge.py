import os.path
import psycopg2
import pygit2
import yaml

class ConfigurationException(Exception):
  def __init__(self, value):
    self.value = value
  def __str__(self):
    return repr(self.value)

def commit_cherrypick(repo, branch, commit, committer):
    """
    Applies a previously cherrypicked commit
    """
    tree = repo.TreeBuilder(commit.tree).write()
    parent_oid = None
    branch_ref = repo.lookup_reference('refs/heads/' + branch.branch_name)
    # Use a loop to pop the first item from the iterator
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

def raise_pr(repo_name, title, body, head, base, git_username, git_password):
    """
    Raise a pull request against the given GitHub repository
    """
    request = {
        'title': title,
        'body': body,
        'head': head,
        'base': base
    }

    buffer = StringIO()
    c = pycurl.Curl()
    c.setopt(c.URL, 'https://api.github.com/repos/%s/pulls' % repo_name)
    c.setopt(c.POST, 1)
    c.setopt(c.POSTFIELDS, json.dumps(request))
    c.setopt(c.HTTPHEADER, ["Content-Type: application/json; charset=utf-8"])
    c.setopt(c.USERNAME, git_username)
    c.setopt(c.PASSWORD, git_password)
    c.setopt(c.WRITEDATA, buffer)
    c.perform()
    status_code = c.getinfo(c.RESPONSE_CODE)
    c.close()

    if status_code != 200:
        raise Exception("Returned status from GitHub API was %d, expected  200 (OK)" % status_code)
    return json.load(buffer)

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
