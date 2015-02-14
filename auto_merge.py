import os.path
import psycopg2
import yaml

class ConfigurationException(Exception):
  def __init__(self, value):
    self.value = value
  def __str__(self):
    return repr(self.value)

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
