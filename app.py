import warnings
import base64

warnings.filterwarnings('ignore')
import cv2
from deepface import DeepFace
# import psycopg2
from psycopg2.extras import RealDictCursor
from psycopg2.pool import SimpleConnectionPool
# import time
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
import os
from fastapi.responses import FileResponse
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import numpy as np
# import threading
# from contextlib import asynccontextmanager
from pydantic import BaseModel
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('background_processor.log'),
        logging.StreamHandler()
    ]
)


class ImageData(BaseModel):
    image: str  # base64 string
    name: str | None = None  # optional, only for new user
    designation: str | None = None  # optional, only for new user


app = FastAPI()
app.mount("/static", StaticFiles(directory="static", html=True), name="static")
#app.add_middleware(
    #CORSMiddleware,
    #allow_origins=["*"],  # or restrict to ["http://localhost:5500"] etc.
    #allow_credentials=True,
    #allow_methods=["*"],
    #allow_headers=["*"],)

logging.info('cors middleware is connected')
SCOPES = ["https://www.googleapis.com/auth/drive"]

creds = None
# Load existing token if it exists
if os.path.exists("token.json"):
    creds = Credentials.from_authorized_user_file("token.json", SCOPES)

service = build("drive", "v3", credentials=creds)  # initializing the connection to google drive
logging.info('Google drive API initialized')
FOLDER_ID = "15ZQ7tSCuk0WgqCE_8V0ZsM-IWZXCSWyv"  # from Drive URL
DB_CONFIG = {
    "host": "aws-1-ap-south-1.pooler.supabase.com",
    "port": 6543,
    "database": "postgres",
    "user": "postgres.qltgyrarlynsvhuvdhbi",
    "password": "cobbvanth618",
    "sslmode": "require"
}
pool = SimpleConnectionPool(1, 10, **DB_CONFIG)

def get_conn():
    return pool.getconn()

def put_conn(conn):
    pool.putconn(conn)


temp_file_name = 'ganesh12.jpg'
table_name = 'faces5'


def capture_image(data):  # capturing image from webcam
    global temp_file_name
    header, encoded = data.image.split(",", 1)
    img_bytes = base64.b64decode(encoded)
    img_array = np.frombuffer(img_bytes, np.uint8)
    frame = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
    cv2.imwrite(temp_file_name, frame)
    query_embedding = DeepFace.represent(frame, model_name="Facenet", enforce_detection=False)[0]["embedding"]
    query_str = "[" + ",".join(str(x) for x in query_embedding) + "]"
    logging.info('image has been successfully captured')
    return query_str


def verify(query_str):
    conn = get_conn()  # verifying the image with the db
    logging.info('connected to db')
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    cursor.execute(
        f"""
        SELECT name, Designation, embedding <-> %s::vector AS distance
        FROM {table_name}
        ORDER BY embedding <-> %s::vector
        LIMIT 5
        """,
        (query_str, query_str))
    logging.info('verification started')
    x = cursor.fetchall()
    cursor.close()
    put_conn(conn)
    logging.info('connection returned to pool')
    return x


def add_new_toDb(name, query_str1, designation):  # adds a new image to db
    conn = get_conn()
    logging.info('connected to db')
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    cursor.execute(f"""INSERT INTO {table_name} (name, embedding, Designation) VALUES (%s, %s::vector, %s)""",
                   (name, query_str1, designation))
    conn.commit()
    logging.info('added to the database')
    cursor.close()
    put_conn(conn)
    logging.info('connection returned to pool')
    return f'added successfully'


def add_new_toDrive(name):  # adds a new image to drive
    file_metadata1 = {"name": name,
                      "parents": [FOLDER_ID]}
    media1 = MediaFileUpload(name, resumable=True)
    file1 = service.files().create(
        body=file_metadata1, media_body=media1, fields="id"
    ).execute()
    logging.info('added to the drive folder')


@app.get("/", include_in_schema=False)
def root():
    return FileResponse("static/index.html")


@app.post("/tests")
def test33(data: ImageData):
    try:
        # Decode base64
        query_str = capture_image(data)
        logging.info(f'length of image {len(data.image)}')
        # res = verify(query_str)
        # x = res[0]['name']

        if data.name and data.designation != 'guest':
            file_name = f'{data.name}.jpg'
            os.rename(temp_file_name, file_name)
            add_new_toDb(data.name, query_str, data.designation)
            add_new_toDrive(file_name)  # you might want to save frame instead of old file_name
            os.remove(file_name)
            logging.info('new users information has been added to the db and drive')
            return {
                "status": "registered",
                "message": f"✅ {data.name} ({data.designation}) has been registered and attendance marked",
                "name": data.name,
                "designation": data.designation}
        elif data.name and data.designation == 'guest':
            logging.info('a guest is trying to register so only temporarily register them')
            os.remove(temp_file_name)
            return {
                "status": "registered",
                "message": f"✅ {data.name} ({data.designation}) has been temporarily registered and attendance marked",
                "name": data.name,
                "designation": data.designation}

        # Otherwise → try to verify
        res = verify(query_str)
        x = res[0]['name']
        desig = res[0]['designation']

        if res[0]['distance'] >= 4.5:  # not recognized
            logging.info('new user trying to register')
            return {
                "status": "new_user",
                "message": "❌ Face not recognized. Please provide your name and designation."
            }
        else:
            logging.info('verification successful')
            os.remove(temp_file_name)
            return {
                "status": "success",
                "message": f"✅ Attendance marked for {x} ({desig})",
                "name": x,
                "designation": desig
            }

    except Exception as e:
        logging.info(f'error is {e}')
        return {"status": "error", "message": f"Error: {str(e)}"}
