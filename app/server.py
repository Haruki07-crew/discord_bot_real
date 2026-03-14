from threading import Thread
from fastapi import FastAPI
import uvicorn

app = FastAPI()

@app.api_route("/", methods=["GET", "HEAD"])
async def root():
    return {"message": "Server is Online."}

def start():
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")

def server_thread():
    t = Thread(target=start, daemon=True)
    t.start()