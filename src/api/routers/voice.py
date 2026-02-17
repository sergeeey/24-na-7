"""Роутер для распознавания intent через Voiceflow RAG."""
from fastapi import APIRouter, HTTPException, Request

from src.utils.logging import get_logger

logger = get_logger("api.voice")
router = APIRouter(prefix="/voice", tags=["voice"])


@router.post("/intent")
async def recognize_intent(request: Request):
    """
    Распознавание intent через Voiceflow RAG или GPT-mini fallback.
    
    **Тело запроса:**
    ```json
    {
        "text": "текст для распознавания intent",
        "user_id": "user123"
    }
    ```
    
    **Пример запроса:**
    ```bash
    curl -X POST "http://localhost:8000/voice/intent" \\
         -H "Content-Type: application/json" \\
         -d '{"text": "напомни мне позвонить маме", "user_id": "user123"}'
    ```
    
    **Пример ответа:**
    ```json
    {
        "intent": "reminder",
        "confidence": 0.95,
        "entities": {
            "action": "позвонить",
            "target": "маме"
        }
    }
    ```
    
    **Ошибки:**
    - `400`: text обязателен
    - `500`: Ошибка распознавания intent
    """
    try:
        body = await request.json()
        text = body.get("text", "")
        user_id = body.get("user_id", "default")
        
        if not text:
            raise HTTPException(status_code=400, detail="text is required")
        
        from src.voice_agent.voiceflow_rag import get_voiceflow_client
        
        client = get_voiceflow_client()
        result = client.recognize_intent(text, user_id=user_id)
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("intent_recognition_failed", error=str(e))
        raise HTTPException(status_code=500, detail=f"Intent recognition failed: {str(e)}")
