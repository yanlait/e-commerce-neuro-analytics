from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from ...agent.planner import answer

router = APIRouter()


class ChatRequest(BaseModel):
    question: str
    history: list[dict] = []


class ChatResponse(BaseModel):
    sql: str | None
    data: list[dict] | None
    chunks: list[dict]


@router.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    try:
        result = answer(req.question, req.history)
        return ChatResponse(**result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
