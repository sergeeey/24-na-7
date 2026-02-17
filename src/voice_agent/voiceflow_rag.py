"""
Voiceflow RAG интеграция для intent recognition.
Reflexio 24/7 — November 2025 Integration Sprint
"""
from typing import Dict, Any, Optional
import os
import requests

from src.utils.logging import get_logger

logger = get_logger("voice_agent.voiceflow")


class VoiceflowRAG:
    """Клиент для Voiceflow RAG API."""
    
    def __init__(self, api_key: Optional[str] = None, version_id: Optional[str] = None):
        """
        Инициализация Voiceflow RAG клиента.
        
        Args:
            api_key: API ключ Voiceflow
            version_id: Version ID проекта
        """
        self.api_key = api_key or os.getenv("VOICEFLOW_API_KEY")
        self.version_id = version_id or os.getenv("VOICEFLOW_VERSION_ID")
        self.base_url = "https://api.voiceflow.com/v2"
        
        if not self.api_key:
            logger.warning("voiceflow_api_key_not_set")
        if not self.version_id:
            logger.warning("voiceflow_version_id_not_set")
    
    def recognize_intent(self, text: str, user_id: str = "default") -> Dict[str, Any]:
        """
        Распознаёт intent из текста.
        
        Args:
            text: Текст для анализа
            user_id: ID пользователя
            
        Returns:
            {
                "intent": str,
                "confidence": float,
                "entities": List[Dict],
            }
        """
        if not self.api_key or not self.version_id:
            logger.warning("voiceflow_not_configured", fallback="gpt_mini")
            return self._fallback_intent(text)
        
        try:
            response = requests.post(
                f"{self.base_url}/interact/{self.version_id}",
                headers={
                    "Authorization": self.api_key,
                    "Content-Type": "application/json",
                },
                json={
                    "action": {
                        "type": "text",
                        "payload": text,
                    },
                    "config": {
                        "tts": False,
                        "stripSSML": True,
                        "stopAll": False,
                        "excludeTypes": ["block", "debug", "flow"],
                    },
                },
                timeout=5,
            )
            
            if response.status_code == 200:
                data = response.json()
                
                # Извлекаем intent из ответа
                intent = data.get("trace", [{}])[0].get("payload", {}).get("intent", "unknown")
                confidence = data.get("trace", [{}])[0].get("payload", {}).get("confidence", 0.0)
                
                return {
                    "intent": intent,
                    "confidence": confidence,
                    "entities": data.get("trace", [{}])[0].get("payload", {}).get("entities", []),
                    "provider": "voiceflow",
                }
            else:
                logger.warning("voiceflow_api_error", status=response.status_code, fallback="gpt_mini")
                return self._fallback_intent(text)
                
        except Exception as e:
            logger.error("voiceflow_request_failed", error=str(e), fallback="gpt_mini")
            return self._fallback_intent(text)
    
    def _fallback_intent(self, text: str) -> Dict[str, Any]:
        """Fallback на GPT-mini при недоступности Voiceflow."""
        try:
            from src.llm.providers import OpenAIClient
            
            client = OpenAIClient(model="gpt-4o-mini")
            
            prompt = f"""Определи intent из следующего текста. Верни только JSON:
{{
    "intent": "название_intent",
    "confidence": 0.0-1.0,
    "entities": []
}}

Текст: {text}
"""
            
            response = client.call(prompt, system_prompt="Ты — эксперт по распознаванию намерений.")
            
            if response.get("text"):
                import json
                try:
                    result_text = response["text"]
                    if "```json" in result_text:
                        result_text = result_text.split("```json")[1].split("```")[0].strip()
                    
                    result = json.loads(result_text)
                    result["provider"] = "gpt_mini_fallback"
                    return result
                except json.JSONDecodeError:
                    pass
            
            # Если парсинг не удался, возвращаем базовый intent
            return {
                "intent": "unknown",
                "confidence": 0.5,
                "entities": [],
                "provider": "gpt_mini_fallback",
            }
            
        except Exception as e:
            logger.error("fallback_intent_failed", error=str(e))
            return {
                "intent": "unknown",
                "confidence": 0.0,
                "entities": [],
                "provider": "error",
            }


def get_voiceflow_client() -> VoiceflowRAG:
    """Фабричная функция для получения Voiceflow клиента."""
    return VoiceflowRAG()





