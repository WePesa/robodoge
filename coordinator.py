#!/usr/bin/python3
from flask import Flask, jsonify
from flask.ext.httpauth import HTTPBasicAuth
import robodoge
import psycopg2
import psycopg2.extras

app = Flask(__name__)
auth = HTTPBasicAuth()
config = robodoge.load_configuration('config.yml')
try:
    merger = robodoge.Robodoge(config)
except robodoge.ConfigurationError as err:
    print(err.msg)
    sys.exit(1)

@auth.get_password
def get_password(username):
    if username == 'automerge':
        return config['http_auth']['password']
    return None

@auth.error_handler
def unauthorized():
    return make_response(jsonify({'error': 'Unauthorized access'}), 401)

@app.route('/automerge/api/v1.0/pr/', methods=['GET'])
def get_prs():
    rows = None
    conn = merger.get_connection()
    try:
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        try:
            cursor.execute("""SELECT id,url,state,title,user_login,html_url,assignee_login,milestone_title,base_ref, build_node, s3_arn, test_node
                              FROM pull_request
                              WHERE project='dogecoin/dogecoin' and state!='closed'
                              ORDER BY id DESC""")
            rows = cursor.fetchall()
        finally:
            cursor.close()

        if rows:
            return jsonify({'prs': rows})
        else:
            return jsonify({'prs': []})
    finally:
        conn.close()

@auth.login_required
@app.route('/automerge/api/v1.0/pr/<int:pr_id>', methods=['POST'])
def update_pr(pr_id):
    rows = None
    conn = merger.get_connection()
    try:
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT id,url,state,title,user_login,html_url,assignee_login,milestone_title,base_ref, build_node, s3_arn, test_node FROM pull_request WHERE project='dogecoin' and state!='closed'")
            rows = cur.fetchall()
        finally:
            cursor.close()

        if rows:
            return jsonify({'prs': rows})
        else:
            return jsonify({'prs': []})
    finally:
        conn.close()

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0')
