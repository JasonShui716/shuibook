from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pathlib import Path

from app.api.routes import router
from app.config import settings

app = FastAPI(title="Shuibook API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"] ,
    allow_headers=["*"],
)

app.include_router(router)

Path(settings.media_dir).mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory="/app/app/static"), name="static")
app.mount("/media", StaticFiles(directory=settings.media_dir), name="media")


@app.get("/api/health")
def health():
    return {"status": "ok"}
