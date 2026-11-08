import os
from threading import Thread
from fastapi import FastAPI
from fastapi.responses import JSONResponse
import uvicorn

app = FastAPI()

# main.py が設定する。() -> (正常か, 詳細の dict) を返す関数
health_provider = None


@app.api_route("/", methods=["GET", "HEAD"])
async def root():
  return {"message": "Server is Online."}


@app.get("/health")
def health():
  # async にしない: bot_health は SQLite を同期的に読むので、FastAPI のスレッドプールで実行させる
  """Bot が Discord に接続していて、データの同期が止まっていなければ 200、そうでなければ 503。
  Docker の healthcheck (compose.yaml) から使う。"""
  if health_provider is None:
    return JSONResponse({"ok": False, "reason": "starting"}, status_code=503)
  try:
    ok, detail = health_provider()
  except Exception as e:
    return JSONResponse({"ok": False, "reason": f"{type(e).__name__}: {e}"}, status_code=503)
  return JSONResponse({"ok": ok, **detail}, status_code=200 if ok else 503)


def start():
  port = int(os.getenv("PORT", 8000))
  uvicorn.run(app, host="0.0.0.0", port=port, log_level="warning")


def server_thread():
  t = Thread(target=start, daemon=True)
  t.start()
