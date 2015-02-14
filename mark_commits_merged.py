import psycopg2
from io import BytesIO
import auto_merge
import sys

def mark_commit_as_merged(cursor, commit_id):
    if len(commit_id) != 40:
        print('Found mangled commit ID %s.' % commit_id)
        return False
    else:
        # TODO: Check the commit exists
        print('Marking commit %s as merged' % commit_id)
        cursor.execute("""UPDATE pull_request_commit SET merged='t' WHERE sha=%(commit_id)s""", {'commit_id': commit_id})
        return True

if len(sys.argv) < 2:
    print('Expected filename of file containing commits which have been merged already as parameter')
    sys.exit(1)
commit_filename = sys.argv[1].strip()

config = auto_merge.load_configuration('config.yml')
conn = auto_merge.get_connection(config)
try:
    cursor = conn.cursor()
    try:
        with open(commit_filename, "r") as commit_file:
            commit_id = commit_file.readline()
            while commit_id:
                mark_commit_as_merged(cursor, commit_id.strip())
                commit_id = commit_file.readline()
        conn.commit()
    finally:
        cursor.close()
finally:
    conn.close()
