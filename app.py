from fastapi import FastAPI
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import psycopg2
from psycopg2.extras import RealDictCursor
from psycopg2.pool import SimpleConnectionPool
import os, time, uuid, json

# ----------------------------
# Database Config
# ----------------------------
DB_CONFIG = {
    "host": "aws-1-ap-south-1.pooler.supabase.com",
    "port": 6543,
    "dbname": "postgres",   # psycopg2 uses 'dbname', not 'database'
    "user": "postgres.qltgyrarlynsvhuvdhbi",
    "password": "cobbvanth618",
    "sslmode": "require"
}

# ----------------------------
# Connection Pool
# ----------------------------
pool = None
while pool is None:
    try:
        pool = SimpleConnectionPool(minconn=1, maxconn=10, **DB_CONFIG)
        print("✅ Connection pool created")
    except Exception as e:
        print(f"❌ Error connecting to DB: {e}")
        time.sleep(5)

def get_conn():
    return pool.getconn()

def put_conn(conn):
    pool.putconn(conn)

# ----------------------------
# FastAPI App
# ----------------------------
app = FastAPI(default_response_class=JSONResponse)
app.mount("/static", StaticFiles(directory="static"), name="static")

# ----------------------------
# Models
# ----------------------------
class ImageData(BaseModel):
    image: str  # base64

class RegisterData(BaseModel):
    image: str
    name: str
    designation: str

# ----------------------------
# Routes
# ----------------------------
@app.get("/", include_in_schema=False)
def root():
    return FileResponse("static/index.html")


@app.post("/tests")
def submit_job(data: ImageData):
    """Enqueue job for worker"""
    conn = get_conn()
    try:
        cursor = conn.cursor()
        job_id = str(uuid.uuid4())
        cursor.execute("""
            INSERT INTO jobs (id, status, image_base64, created_at, updated_at)
            VALUES (%s, 'pending', %s, NOW(), NOW())
        """, (job_id, data.image))
        conn.commit()
        cursor.close()
        return {"job_id": job_id, "status": "pending"}
    finally:
        put_conn(conn)


@app.get("/status/{job_id}")
def check_status(job_id: str):
    """Check job status/result"""
    conn = get_conn()
    try:
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute("SELECT status, result FROM jobs WHERE id=%s", (job_id,))
        job = cursor.fetchone()
        cursor.close()

        if not job:
            return JSONResponse(status_code=404, content={"error": "Job not found"})

        return {"job_id": job_id, "status": job["status"], "result": job["result"]}
    finally:
        put_conn(conn)


@app.post("/register")
def register_user(data: RegisterData):
    """Register a new user into faces table"""
    conn = get_conn()
    try:
        cursor = conn.cursor(cursor_factory=RealDictCursor)

        # Insert into faces
        cursor.execute("""
            INSERT INTO faces (name, designation, embedding, created_at)
            VALUES (%s, %s, NULL, NOW())
            RETURNING id
        """, (data.name, data.designation))
        face_id = cursor.fetchone()["id"]

        # Enqueue job for embedding computation
        job_id = str(uuid.uuid4())
        cursor.execute("""
            INSERT INTO jobs (id, status, image_base64, result, created_at, updated_at)
            VALUES (%s, 'pending', %s, %s::jsonb, NOW(), NOW())
        """, (
            job_id,
            data.image,
            json.dumps({"register_face_id": face_id,
                       "name":data.name,
                       "designation":data.designation})
        ))

        conn.commit()
        cursor.close()

        return {
            "status": "registered",
            "message": f"✅ {data.name} ({data.designation}) registered successfully.",
            "face_id": face_id,
            "job_id": job_id
        }
    finally:
        put_conn(conn)
