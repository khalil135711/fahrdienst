import os

import psycopg

DB_URL = os.environ["DATABASE_URL"]


def db():
    return psycopg.connect(DB_URL)
