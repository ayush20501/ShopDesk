import json
import logging
import sqlite3
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import actions
from .config import load_settings
from .graph import SupportDesk

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
log = logging.getLogger("shopdesk.api")

STATIC = Path(__file__).parent / "static"
state = {}


@asynccontextmanager
async def lifespan(app):
    settings = load_settings()
    if not settings.db_path.exists():
        raise RuntimeError("data/shop.db is missing. Run: python data/seed.py")
    state["settings"] = settings
    state["desk"] = SupportDesk(settings)
    state["desk"].retriever.search("warm up")
    yield


app = FastAPI(title="ShopDesk", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=STATIC), name="static")


class Turn(BaseModel):
    role: str = Field(pattern="^(user|assistant)$")
    content: str = Field(max_length=2000)


class ChatIn(BaseModel):
    customer_id: int
    message: str = Field(min_length=1, max_length=1000)
    history: list[Turn] = Field(default_factory=list, max_length=12)


def _customers():
    conn = sqlite3.connect(state["settings"].db_path)
    try:
        return conn.execute("SELECT id, name, city, tier FROM customers ORDER BY id").fetchall()
    finally:
        conn.close()


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/customers")
def customers():
    return [{"id": i, "name": n, "city": c, "tier": t} for i, n, c, t in _customers()]


@app.post("/chat")
def chat(body: ChatIn):
    if body.customer_id not in {c[0] for c in _customers()}:
        raise HTTPException(404, "unknown customer")
    history = [t.model_dump() for t in body.history]
    try:
        return state["desk"].ask(body.customer_id, body.message, history)
    except Exception:
        log.exception("chat failed")
        raise HTTPException(502, "The assistant is unavailable right now. Please try again.")


@app.post("/chat/stream")
def chat_stream(body: ChatIn):
    if body.customer_id not in {c[0] for c in _customers()}:
        raise HTTPException(404, "unknown customer")
    history = [t.model_dump() for t in body.history]

    def events():
        try:
            for event in state["desk"].ask_stream(body.customer_id, body.message, history):
                if event["type"] == "done":
                    event.pop("trace", None)
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        except Exception:
            log.exception("chat stream failed")
            error = {"type": "error", "message": "The assistant is unavailable right now. Please try again."}
            yield f"data: {json.dumps(error)}\n\n"

    headers = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
    return StreamingResponse(events(), media_type="text/event-stream", headers=headers)


@app.get("/actions")
def pending(status: str = "pending"):
    if status not in ("pending", "approved", "rejected"):
        raise HTTPException(400, "status must be pending, approved or rejected")
    return actions.list_pending(state["settings"], status)


@app.post("/actions/{action_id}/{decision}")
def decide(action_id: int, decision: str):
    if decision not in ("approve", "reject"):
        raise HTTPException(404, "unknown decision")
    result = actions.resolve(state["settings"], action_id, decision == "approve")
    if result["status"] == "missing":
        raise HTTPException(404, result["message"])
    return result
