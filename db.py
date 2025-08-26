from dotenv import load_dotenv
from models import WrongDatabase
import pymysql
import os

load_dotenv()

DB_HOST = os.getenv("DB_HOST")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_MAIN_NAME = os.getenv("DB_MAIN_NAME")
DB_MNETWORK_NAME = os.getenv("DB_MNETWORK_NAME")

def get_connection(database = "main"):
    if database == "main":
        return pymysql.connect(
            host=DB_HOST,
            user=DB_USER,
            password=DB_PASSWORD,
            database=DB_MAIN_NAME,
            cursorclass=pymysql.cursors.Cursor
        )
    elif database == "mnetwork":
        return pymysql.connect(
            host=DB_HOST,
            user=DB_USER,
            password=DB_PASSWORD,
            database=DB_MNETWORK_NAME,
            cursorclass=pymysql.cursors.Cursor
        )
    else:
        raise WrongDatabase
    
def get_dict_connection(database = "main"):
    if database == "main":
        return pymysql.connect(
            host=DB_HOST,
            user=DB_USER,
            password=DB_PASSWORD,
            database=DB_MAIN_NAME,
            cursorclass=pymysql.cursors.DictCursor
        )
    elif database == "mnetwork":
        return pymysql.connect(
            host=DB_HOST,
            user=DB_USER,
            password=DB_PASSWORD,
            database=DB_MNETWORK_NAME,
            cursorclass=pymysql.cursors.DictCursor
        )
    else:
        raise WrongDatabase