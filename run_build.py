#!/usr/bin/python3

import re
import os
import string
import sys
import subprocess
import auto_merge

def compile_dogecoin():
  path = os.getcwd()
  subprocess.check_output([path + os.path.sep + 'autogen.sh'])
  subprocess.check_output([path + os.path.sep + 'configure'])
  subprocess.check_output(['make', 'clean'], stderr=subprocess.STDOUT)
  subprocess.check_output(['make'], stderr=subprocess.STDOUT)
  subprocess.check_output(['make', 'check'], stderr=subprocess.STDOUT)
  return True

config = auto_merge.load_configuration('config.yml')
if not 'dogecoin_repo' in config:
    print('Missing "dogecoin_repo" configuration.')
    sys.exit(1)

if not config['dogecoin_repo']['path']:
    print('Missing "dogecoin_repo" configuration.')
    sys.exit(1)

cwd = os.getcwd()
os.chdir(config['dogecoin_repo']['path'])
os.chdir('..') # Go up to the directory above the Git repository
build_success = compile_dogecoin()
os.chdir(cwd)
