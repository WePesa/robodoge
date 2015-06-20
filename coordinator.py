#!/usr/bin/python3
from robodoge.coordinator import app as application

application.config['DEBUG'] = True
application.run()
