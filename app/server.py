import os
from threading import Thread
from fastapi import FastAPI
import uvicorn

app = FastAPI()

@app.api_route("/", methods=["GET", "HEAD"])
async def root():
    return {"message": "Server is Online."}

def start():
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")

def server_thread():
    t = Thread(target=start, daemon=True)
    t.start()