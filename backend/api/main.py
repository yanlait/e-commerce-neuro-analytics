from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .routes import chat

app = FastAPI(title="Analytics Assistant API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat.router, prefix="/api")
