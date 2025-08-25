from google.oauth2 import service_account
from googleapiclient.discovery import build
import numpy as np
import cv2
from deepface import DeepFace
import psycopg2
from psycopg2.extras import RealDictCursor

conn = psycopg2.connect(host='host', database='db', user='usr', password='password',
                        cursor_factory=RealDictCursor)
cursor = conn.cursor()


def add_new(query_str1, name):
    image_url = f'{name}.jpg'
    cursor.execute("INSERT INTO faces3 (name, embedding, image_url) VALUES (%s, %s::vector, %s)",
                   (name, query_str1, image_url))
    conn.commit()


def create_tabel1():
    cursor.execute("""
        CREATE TABLE faces3 (
        id SERIAL PRIMARY KEY,
        name TEXT,
        embedding vector(512),  -- 512 for ArcFace, adjust if using other model
        image_url TEXT
    );
    """)
    conn.commit()


# Path to your downloaded JSON key
SERVICE_ACCOUNT_FILE = "service_account.json"
SCOPES = ["https://www.googleapis.com/auth/drive"]

# Authenticate using the service account
creds = service_account.Credentials.from_service_account_file(
    SERVICE_ACCOUNT_FILE, scopes=SCOPES
)

service = build("drive", "v3", credentials=creds)


def fill_table():
    # Example: list files in a shared folder
    FOLDER_ID = "FOLDER_ID"  # from Drive URL
    query = f"'{FOLDER_ID}' in parents and trashed=false"

    results = service.files().list(q=query, fields="files(id, name, mimeType)").execute()
    drive_files = results.get("files", [])

    if not drive_files:
        print("No files found.")
    else:
        for item in drive_files:
            print(f"{item['name']} ({item['id']})")
    for file in drive_files:
        file_id = file['id']
        file_name = file['name']
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
            add_new(embedding_str, file_name)
            print(embedding)
        except Exception as e:
            print(f"❌ Error downloading {file_name}: {e}")
            continue


cursor.close()
conn.close()


