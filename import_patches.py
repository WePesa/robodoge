#!/usr/bin/python

import mysql.connector
from mysql.connector import errorcode
import re
import os
import string
import sys
import auto_merge
import email

def import_patch(cursor, patch_filename):
  """
  Import a patch into the database. Takes in a database cursor and name of a file
  to parse.
  """
  with open(patch_filename, "r") as patch_file:

    # First line is special
    commit_line = patch_file.readline()
    commit_match = re.match('From ([0-9a-f]{40}) [A-z]{3} [A-z]{3} [0-9]{1,2} 00:00:00 [0-9]{4}', commit_line)
    if not commit_match:
      print 'Could not parse commit from line: ' + commit_line
      return
    commit = commit_match.group(1)

    # Parse the rest of the patch like an email
    message = email.message_from_string(patch_file.read())
    (from_name, from_address) = email.utils.parseaddr(message['From'])

    patch_match = re.match('\[PATCH ([0-9]+)/[0-9]+\] (.+)', message['subject'])
    if not patch_match:
      print 'Could not parse patch sequence number from subject line: ' + subject
      return
    sequence = patch_match.group(1)
    subject = string.join(patch_match.group(2).splitlines())
    body = message.get_payload()
    (description, sep, remainder) = body.partition('---')
    (summary, sep, patch_payload) = remainder.partition('\n\n')

    add_patch = ("INSERT INTO patch "
      "(btc_commit_id, batch, batch_sequence, author_name, author_email, subject, descript, raw) "
      "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)")
    data_patch = (commit, 1, sequence, from_name, from_address, subject, description.strip(), message.get_payload())
    cursor.execute(add_patch, data_patch)
    # TODO: Import individual parts
  return

try:
  cnx = auto_merge.get_connection('config.yml')
  try:
    cursor = cnx.cursor()
    try:
      for file in os.listdir('patches'):
        import_patch(cursor, 'patches/' + file)
      cnx.commit()
    finally:
      cursor.close()

  finally:
    cnx.close()
except mysql.connector.Error as err:
  print err
  sys.exit(1)
