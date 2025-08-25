import cv2
import warnings
import base64

warnings.filterwarnings('ignore')
from deepface import DeepFace
import psycopg2
from psycopg2.extras import RealDictCursor
import time
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import numpy as np
import threading
from contextlib import asynccontextmanager
from pydantic import BaseModel


class ImageData(BaseModel):
    image: str  # base64 string


@asynccontextmanager
async def lifespan(app: FastAPI):
    thread = threading.Thread(target=check, daemon=True)
    thread.start()
    yield


app = FastAPI(lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # or restrict to ["http://localhost:5500"] etc.
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

SCOPES = ["https://www.googleapis.com/auth/drive"]

creds = None
# Load existing token if it exists
if os.path.exists("token.json"):
    creds = Credentials.from_authorized_user_file("token.json", SCOPES)

service = build("drive", "v3", credentials=creds)  # initializing the connection to google drive
FOLDER_ID = "15ZQ7tSCuk0WgqCE_8V0ZsM-IWZXCSWyv"  # from Drive URL
# file_metadata = {"name": "img1"}
# media = MediaFileUpload("img1.jpg", resumable=True)
# file = service.files().create(
# body=file_metadata, media_body=media, fields="id"
# ).execute()

# print("Uploaded File ID:", file.get("id"))
while True:  # initialized the connection to the postgres db
    try:
        conn = psycopg2.connect(host='localhost', database='recog', user='postgres', password='cobbvanth618',
                                cursor_factory=RealDictCursor)
        # cursor = conn.cursor()
        print('connection successful')
        break
    except Exception as error:
        print('connection failed')
        time.sleep(2)
cursor = conn.cursor()
file_name = 'ganesh12.jpg'
table_name = 'faces1'


def capture_image():  # capturing image from webcam
    global file_name
    cam = cv2.VideoCapture(0, cv2.CAP_DSHOW)
    ret, frame = cam.read()
    if ret:
        cv2.imshow("Captured", frame)
        cv2.imwrite(file_name, frame)
        cv2.waitKey(10)
        # cv2.destroyWindow("Captured")
    else:
        return 'Failed capture image'
    cam.release()
    query_embedding = DeepFace.represent(img_path=frame, model_name="ArcFace")[0]["embedding"]
    query_str = "[" + ",".join(str(x) for x in query_embedding) + "]"
    return query_str


def verify(query_str):  # verifying the image with the db
    cursor.execute(
        f"""
        SELECT name, image_url, embedding <-> %s::vector AS distance
        FROM {table_name}
        ORDER BY embedding <-> %s::vector
        LIMIT 5
        """,
        (query_str, query_str))
    return cursor.fetchall()


def add_new_toDb(name, query_str1):  # adds a new image to db
    image_url = f'{name}jpg.'
    cursor.execute(f"""INSERT INTO {table_name} (name, embedding, image_url) VALUES (%s, %s::vector, %s)""",
                   (name, query_str1, image_url))
    conn.commit()
    return f'added successfully'


def add_new_toDrive(name):  # adds a new image to drive
    file_metadata1 = {"name": name,
                      "parents": [FOLDER_ID]}
    media1 = MediaFileUpload(name, resumable=True)
    file1 = service.files().create(
        body=file_metadata1, media_body=media1, fields="id"
    ).execute()


def check():  # checks if an image was manually added to the drive and reflects that change in the db
    while True:
        try:
            query = f"'{FOLDER_ID}' in parents and trashed=false"
            results = service.files().list(
                q=query,
                fields="files(id, name, mimeType, createdTime)",
                orderBy="createdTime desc",
            ).execute()
            drive_files = results.get("files", [])
            drive_length = len(drive_files)

            cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
            db_length = cursor.fetchone()["count"]
            if drive_length > db_length:
                diff = drive_length - db_length
                for new_file in drive_files[:diff]:
                    file_id = new_file['id']
                    file_name1 = new_file['name']
                    try:
                        request = service.files().get_media(fileId=file_id)
                        image_content = request.execute()
                        np_arr = np.frombuffer(image_content, np.uint8)
                        img = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
                        embedding = \
                            DeepFace.represent(img,
                                               model_name='ArcFace')[0][
                                'embedding']
                        embedding_str = "[" + ",".join(str(x) for x in embedding) + "]"
                        add_new_toDb(query_str1=embedding_str, name=file_name1)
                        # print(embedding)
                    except Exception as e:
                        # maybe try deleting the duplicate image in drive
                        # changing the embedding column to the primary key in the db ensures uniqueness
                        print(f"❌ Error downloading {file_name1}: {e}")
            time.sleep(300)  # prevent 100% CPU spin
        except Exception as e:
            print(f"❌ Error in Drive check loop: {e}")
            time.sleep(300)


@app.get('/')
def root():
    return {'message': 'hello world'}


@app.get("/records")
def get_records():
    cursor.execute(f"SELECT name, image_url, timestamp FROM {table_name}")
    return cursor.fetchall()


@app.post("/tests")
def test33(data: ImageData):
    try:
        # Decode base64
        header, encoded = data.image.split(",", 1)
        img_bytes = base64.b64decode(encoded)
        img_array = np.frombuffer(img_bytes, np.uint8)
        frame = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
        cv2.imwrite(file_name, frame)
        query_embedding = DeepFace.represent(frame, model_name="ArcFace")[0]["embedding"]
        query_str = "[" + ",".join(str(x) for x in query_embedding) + "]"
        res = verify(query_str)
        x = res[0]['name']
        if res[0]['distance'] >= 4.5:  # this means someone new is trying to register
            add_new_toDb('ganesh', query_str)
            add_new_toDrive(file_name)
            # os.remove(file_name)
            return {"message": "✅ Your attendance has been marked ganesh"}
        else:
            return {"message": f"✅ Your attendance has been marked {x}"}

    except Exception as e:
        return {"message": f"Error: {str(e)}"}
