from datetime import datetime
from typing import Optional
import os

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import httpx

app = FastAPI(title="PAL 2026 Router", version="1.0.0-phase1")

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://ollama:11434")
DEFAULT_MODEL = os.getenv("DEFAULT_MODEL", "llama3.3:70b-instruct-q4_K_M")
DEFAULT_NUM_CTX = int(os.getenv("DEFAULT_NUM_CTX", "8192"))


class QueryRequest(BaseModel):
    prompt: str
    model: Optional[str] = None
    system: Optional[str] = None
    stream: bool = False
    temperature: Optional[float] = 0.7


class HealthResponse(BaseModel):
    status: str
    timestamp: str
    ollama_available: bool
    loaded_models: list
    default_model: str
    phase: str


@app.get("/health", response_model=HealthResponse)
async def health():
    async with httpx.AsyncClient() as client:
        try:
            r = await client.get(f"{OLLAMA_URL}/api/tags", timeout=5.0)
            loaded = [m["name"] for m in r.json().get("models", [])]
            ollama_ok = True
        except Exception:
            loaded = []
            ollama_ok = False
    return HealthResponse(
        status="green" if ollama_ok else "red",
        timestamp=datetime.utcnow().isoformat(),
        ollama_available=ollama_ok,
        loaded_models=loaded,
        default_model=DEFAULT_MODEL,
        phase="phase-1-a6000",
    )


@app.post("/query")
async def query(req: QueryRequest):
    model = req.model or DEFAULT_MODEL
    payload = {
        "model": model,
        "prompt": req.prompt,
        "stream": req.stream,
        "options": {
            "temperature": req.temperature,
            "num_ctx": DEFAULT_NUM_CTX,
        },
    }
    if req.system:
        payload["system"] = req.system
    async with httpx.AsyncClient() as client:
        try:
            r = await client.post(
                f"{OLLAMA_URL}/api/generate",
                json=payload,
                timeout=300.0,
            )
            r.raise_for_status()
            return r.json()
        except httpx.HTTPError as e:
            raise HTTPException(status_code=500, detail=str(e))


@app.get("/")
async def root():
    return {"service": "PAL 2026 Router", "version": "1.0.0-phase1"}
