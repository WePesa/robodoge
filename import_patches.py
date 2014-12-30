#!/usr/bin/python

import mysql.connector
from mysql.connector import errorcode
import re
import os
import string
import sys
import auto_merge
import email

def import_patch_chunks(cursor, commit, patch_chunks):
  chunks = []
  add_chunk = ("INSERT INTO patch_chunk "
    "(btc_commit_id, from_filename, to_filename, body) "
    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)")
  lines = patch_chunks.split('\n')
  idx = 0

  while idx < len(lines):
    diff_start = idx
    diff_match = re.match('diff --git (\S+) (\S+)', lines[idx])
    if not diff_match:
      raise Exception('Failed to match first diff line: ' + lines[idx])
    idx += 1
    while idx < len(lines) and not lines[idx].find('--- ') == 0:
      idx += 1

    if idx == len(lines):
      # New file
      idx = diff_start + 2
      from_file = diff_match.group(1)
      to_file = diff_match.group(2)
    else:
      from_file = lines[idx][4:].strip()

      idx += 1
      if idx == len(lines) or not lines[idx].find('+++ ') == 0:
        raise Exception('Failed to match +++ diff line: ' + lines[idx])
      to_file = lines[idx][4:].strip()

    # Strip path identifiers
    if from_file.find('a/') == 0:
      from_file = from_file[2:]
    if to_file.find('b/') == 0:
      to_file = to_file[2:]

    idx += 1

    while idx < len(lines) and not re.match('diff --git \S+ \S+', lines[idx]):
      idx += 1

    add_patch = ("INSERT INTO patch_chunk "
      "(btc_commit_id, from_filename, to_filename, body) "
      "VALUES (%s, %s, %s, %s)")
    data_patch = (commit, from_file, to_file, string.join(lines[diff_start: idx - 1], '\n'))
    cursor.execute(add_patch, data_patch)
  return

def import_patch(cnx, cursor, patch_filename):
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
    (summary, sep, patch_chunks) = remainder.partition('\n\n')

    add_patch = ("INSERT INTO patch "
      "(btc_commit_id, batch, batch_sequence, author_name, author_email, subject, descript, raw) "
      "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)")
    data_patch = (commit, 1, sequence, from_name, from_address, subject, description.strip(), message.get_payload())
    cursor.execute(add_patch, data_patch)
    import_patch_chunks(cursor, commit, patch_chunks.strip())

    cnx.commit()
  return

try:
  cnx = auto_merge.get_connection('config.yml')
  try:
    cursor = cnx.cursor()
    try:
      for file in os.listdir('patches'):
        import_patch(cnx, cursor, 'patches/' + file)
    finally:
      cursor.close()

  finally:
    cnx.close()
except mysql.connector.Error as err:
  print err
  sys.exit(1)
