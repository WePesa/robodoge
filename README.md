auto-merge
==========

Automation suite for merging commits from upstream. In this case, heavily specialised towards
merging commits from Bitcoin to Dogecoin.

Scripts are:

* import\_bitcoin\_pull\_requests.py - Read closed pull requests from Bitcoin repo and insert them into the database ready to merge
* import\_dogecoin\_pull\_requests.py - Read open pull requests from Dogecoin repo and insert them into the database ready to test
* mass\_test\_pull\_requests.py - Automatically merge pending pull requests from Bitcoin, run unit tests, bundle successful PRs together and submit back to Dogecoin repo
