from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

app = FastAPI(default_response_class=JSONResponse)

origins = [
    "http://localhost:63342",
    "https://attendance-code.onrender.com",
    "null"  # handle file:// case
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.post("/tests")
async def tests(request: Request):
    data = await request.json()
    return {"msg": "OK", "received": data}
