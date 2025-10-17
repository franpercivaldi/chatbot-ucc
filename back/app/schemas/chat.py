from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from .common import Source

class ChatMeta(BaseModel):
    periodo: Optional[str] = None
    facultad: Optional[str] = None
    carrera: Optional[str] = None
    modalidad: Optional[str] = None
    carrera_id: Optional[str] = None

class ChatRequest(BaseModel):
    message: str
    meta: Optional[ChatMeta] = None
    bot_id: Optional[str] = None
    session_id: Optional[str] = None
    debug: Optional[bool] = False

class ChatResponse(BaseModel):
    answer: str
    sources: List[Source] = []
    retrieval_debug: Optional[Dict[str, Any]] = None
