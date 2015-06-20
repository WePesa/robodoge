#!/usr/bin/python3
from flask import Flask, jsonify
from flask.ext.httpauth import HTTPBasicAuth
import robodoge

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

tasks = [
    {
        'id': 1,
        'title': u'Buy groceries',
        'description': u'Milk, Cheese, Pizza, Fruit, Tylenol', 
        'done': False
    },
    {
        'id': 2,
        'title': u'Learn Python',
        'description': u'Need to find a good Python tutorial on the web', 
        'done': False
    }
]

@app.route('/automerge/api/v1.0/pr/', methods=['GET'])
def get_prs():
    rows = None
    conn = merger.get_connection()
    try:
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT * FROM pull_request WHERE project='dogecoin' and state!='closed'")
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
            cursor.execute("SELECT * FROM pull_request WHERE project='dogecoin' and state!='closed'")
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
