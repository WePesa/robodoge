#!/usr/bin/python3
from flask import Flask, jsonify, request, make_response, abort
import psycopg2
import psycopg2.extras
from . import *

app = Flask(__name__)
config = load_configuration('/var/www/robodoge/config.yml')
try:
    merger = Robodoge(config)
except ConfigurationError as err:
    print(err.msg)
    sys.exit(1)

@app.route('/automerge/api/v1.0/pr/', methods=['GET'])
def get_prs():
    conn = merger.get_connection()
    try:
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        try:
            cursor.execute("""SELECT id, number, url,state,title,user_login,html_url,assignee_login,milestone_title,base_ref, build_node, s3_arn, test_node
                              FROM pull_request
                              WHERE project='dogecoin/dogecoin' and state!='closed'
                              ORDER BY id ASC""")
            return jsonify({'prs': cursor.fetchall()})
        finally:
            cursor.close()
    finally:
        conn.close()

@app.route('/automerge/api/v1.0/pr/build_ready', methods=['GET'])
def get_buildable_prs():
    conn = merger.get_connection()
    try:
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        try:
            cursor.execute("""SELECT id, number, url,state,title,user_login,html_url,assignee_login,milestone_title,base_ref, build_node, s3_arn, test_node
                              FROM pull_request
                              WHERE project='dogecoin/dogecoin' and state='open' and assignee_login is null and milestone_title='1.9' and base_ref='1.9-dev' and build_node IS NULL
                              ORDER BY id ASC""")
            return jsonify({'prs': cursor.fetchall()})
        finally:
            cursor.close()
    finally:
        conn.close()

@app.route('/automerge/api/v1.0/pr/<int:pr_id>', methods=['GET'])
def get_pr(pr_id):
    conn = merger.get_connection()
    try:
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        try:
            cursor.execute("""SELECT id, number, url,state,title,user_login,html_url,assignee_login,milestone_title,base_ref, build_node, s3_arn, test_node
                              FROM pull_request
                              WHERE id=%(id)s""", {'id': pr_id})
            return jsonify({'prs': cursor.fetchall()})
        finally:
            cursor.close()
    finally:
        conn.close()

@app.route('/automerge/api/v1.0/pr/<int:pr_id>', methods=['POST'])
def update_pr(pr_id):
    pr_url = None
    conn = merger.get_connection()
    try:
        cursor = conn.cursor()
        try:
            cursor.execute("""SELECT url
                              FROM pull_request
                              WHERE id=%(id)s""", {'id': pr_id})
            row = cursor.fetchone()
            if not row:
                abort(404)
            else:
                pr_url = row[0].replace('pulls', 'issues')
        finally:
            cursor.close()

        if not request.json or not 'operation' in request.json:
            return jsonify({'result': 'No operation specified'})

        if request.json['operation'] == 'claim_build':
            return claim_pr(conn, pr_id, pr_url, 'rnicoll', request.remote_addr)
        else:
            return jsonify({'result': 'Invalid operation specified'})
    finally:
        conn.close()

def claim_pr(conn, pr_id, pr_url, username, remote_addr):
    # Tell Github we're claiming the PR
    request = {
        'assignee': username
    }
    if not merger.call_github(pr_url, request, 'PATCH'):
        return jsonify({'result': 'failed to call Github'})
    # Update the local database
    cursor = conn.cursor()
    try:
        cursor.execute("""UPDATE pull_request
                          SET assignee_login=%(username)s, build_node=%(remote_addr)s
                          WHERE id=%(id)s""", {'id': pr_id, 'username': username, 'remote_addr': remote_addr})
        conn.commit()
    finally:
        cursor.close()
    # Return a value to let the node know that's okay
    return jsonify({'result': 'success'})
