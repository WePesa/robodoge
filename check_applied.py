#!/usr/bin/python

import mysql.connector
from mysql.connector import errorcode
import re
import os
import string
import sys
import subprocess
import auto_merge

def check_if_applied(cnx, cursor, commit):
  subprocess.check_output(['git', 'reset', '--hard'])
  
  update_patch = ("UPDATE patch SET status=%s WHERE btc_commit_id=%s")
  try:
    subprocess.check_output(['git', 'cherry-pick', commit, '--no-commit', '--strategy=recursive', '--strategy-option=theirs'], stderr=subprocess.STDOUT)
  except subprocess.CalledProcessError as err:
    print "Marking commit " + commit + " as collision"
    cursor.execute(update_patch, ('Collision', commit))
    cnx.commit()
    return

  diff = subprocess.check_output(['git', 'diff', 'HEAD'])
  if (len(diff) == 0):
    print "Marking commit " + commit + " as applied"
    cursor.execute(update_patch, ('Applied', commit))
    cnx.commit()
  else:
    cursor.execute(update_patch, ('Available', commit))
    cnx.commit()
  return

commits = []
query = ("SELECT btc_commit_id FROM patch WHERE status IS NULL ORDER BY batch, batch_sequence")
try:
  cnx = auto_merge.get_connection('config.yml')
  try:
    cursor = cnx.cursor()
    try:
      cursor.execute(query)

      # Copy out the list before we start modifying the database
      for (commit) in cursor:
        commits.append(commit[0])

      print commits
      cwd = os.getcwd()
      os.chdir('dogecoin')
      for commit in commits:
        check_if_applied(cnx, cursor, commit)
      os.chdir(cwd)
    finally:
      cursor.close()

  finally:
    cnx.close()
except mysql.connector.Error as err:
  print err
  sys.exit(1)
