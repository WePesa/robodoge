CREATE TABLE pull_request (
    id INTEGER NOT NULL,
    number INTEGER NOT NULL,
    project VARCHAR(24) NOT NULL,
    url VARCHAR(80) NOT NULL,
    html_url VARCHAR(80) NOT NULL,
    state VARCHAR(12) NOT NULL,
    title TEXT NOT NULL,
    user_login VARCHAR(40),
    body TEXT NOT NULL,
    created_at DATE NOT NULL,
    merged_at DATE DEFAULT NULL,
    merge_commit_sha VARCHAR(40) DEFAULT NULL,
    assignee_login VARCHAR(40) DEFAULT NULL,
    milestone_title VARCHAR(40) DEFAULT NULL,
    base_ref VARCHAR(40) DEFAULT NULL,
    build_node VARCHAR(60) DEFAULT NULL,
    build_started DATE,
    build_failed DATE,
    build_succeeded DATE,
    s3_arn VARCHAR(80),
    test_node VARCHAR(60),
    test_started DATE,
    test_succeeded DATE,
    test_failed DATE,
    PRIMARY KEY(id)
);

CREATE TABLE pull_request_commit (
    pr_id INTEGER NOT NULL REFERENCES pull_request(id),
    ordinality INTEGER NOT NULL DEFAULT '0',
    sha VARCHAR(40) NOT NULL,
    to_merge boolean NOT NULL default FALSE,
    ready_to_merge boolean NOT NULL default FALSE,
    unit_tests_pass boolean default NULL,
    merged boolean NOT NULL default FALSE,
    raised_pr_id INTEGER REFERENCES pull_request(id),
    PRIMARY KEY(pr_id, sha)
);
