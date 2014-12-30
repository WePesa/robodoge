import os.path
import mysql.connector
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

def get_connection(config_filename):
  config = load_configuration(config_filename)
  if 'mysql' not in config:
    raise ConfigurationException("Expected 'mysql' section in configuration file '" + config_filename + "'")
  
  mysql_config = config['mysql']
  if 'username' not in mysql_config or 'db' not in mysql_config:
    raise Exception("Expected MySQL username and database name to be provided in configuration file")

  username = mysql_config['username'].strip()
  if 'password' in mysql_config:
    password = mysql_config['password'].strip()
  else:
    password = ''
  db = mysql_config['db'].strip()
  if 'host' in mysql_config:
    host = mysql_config['host'].strip()
  else:
    host = 'localhost'

  return mysql.connector.connect(user=username, password=password, host=host, database=db)
