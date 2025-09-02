from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import psycopg2
from psycopg2.extras import RealDictCursor
import os, time, uuid, json

DB_CONFIG = {
    "host": "aws-1-ap-south-1.pooler.supabase.com",
    "port": 6543,
    "database": "postgres",
    "user": "postgres.qltgyrarlynsvhuvdhbi",
    "password": "cobbvanth68",
    "sslmode": "require"
}

def get_connection():
    return psycopg2.connect(**DB_CONFIG, cursor_factory=RealDictCursor)

app = FastAPI(default_response_class=JSONResponse)

class ImageData(BaseModel):
    image: str  # base64

class RegisterData(BaseModel):
    image: str
    name: str
    designation: str

@app.post("/tests")
def submit_job(data: ImageData):
    """Enqueue job for worker"""
    conn = get_connection()
    cursor = conn.cursor()
    job_id = str(uuid.uuid4())
    cursor.execute("""
        INSERT INTO jobs (id, status, image_base64, created_at, updated_at)
        VALUES (%s, 'pending', %s, NOW(), NOW())
    """, (job_id, data.image))
    conn.commit()
    cursor.close()
    conn.close()
    return {"job_id": job_id, "status": "pending"}


@app.get("/status/{job_id}")
def check_status(job_id: str):
    """Check job status/result"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT status, result FROM jobs WHERE id=%s", (job_id,))
    job = cursor.fetchone()
    cursor.close()
    conn.close()

    if not job:
        return JSONResponse(status_code=404, content={"error": "Job not found"})

    return {"job_id": job_id, "status": job["status"], "result": job["result"]}


@app.post("/register")
def register_user(data: RegisterData):
    """Register a new user into faces table"""
    conn = get_connection()
    cursor = conn.cursor()

    # Save the embedding/job result from worker if needed
    job_id = str(uuid.uuid4())
    cursor.execute("""
        INSERT INTO faces (name, designation, embedding, created_at)
        VALUES (%s, %s, NULL, NOW())
        RETURNING id
    """, (data.name, data.designation))

    face_id = cursor.fetchone()["id"]

    # Optionally enqueue job to compute embedding from image
    cursor.execute("""
        INSERT INTO jobs (id, status, image_base64, result, created_at, updated_at)
        VALUES (%s, 'pending', %s, %s::jsonb, NOW(), NOW())
    """, (
        job_id,
        data.image,
        json.dumps({"register_face_id": face_id})
    ))

    conn.commit()
    cursor.close()
    conn.close()

    return {
        "status": "registered",
        "message": f"✅ {data.name} ({data.designation}) registered successfully.",
        "face_id": face_id,
        "job_id": job_id
    }
