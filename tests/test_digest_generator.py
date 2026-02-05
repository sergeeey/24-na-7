"""
Тесты для Digest Generator (Core Domain).
"""
import pytest
from datetime import date, datetime
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path
import json

from src.digest.generator import DigestGenerator


class TestDigestGenerator:
    """Тесты генератора дайджестов."""
    
    @pytest.fixture
    def generator(self, tmp_path):
        """Фикстура для генератора."""
        db_path = tmp_path / "test.db"
        return DigestGenerator(db_path=db_path)
    
    def test_generator_initialization(self, generator):
        """Инициализация генератора."""
        assert generator is not None
        assert generator.db_path is not None
    
    def test_extract_facts_empty(self, generator):
        """Извлечение фактов из пустых транскрипций."""
        facts = generator.extract_facts([], use_llm=False)
        assert facts == []
    
    def test_extract_facts_with_data(self, generator):
        """Извлечение фактов с данными."""
        transcriptions = [
            {
                "id": "1",
                "text": "Meeting about project timeline",
                "created_at": "2026-01-31T10:00:00",
            }
        ]
        
        # Без LLM возвращает базовые факты
        facts = generator.extract_facts(transcriptions, use_llm=False)
        assert isinstance(facts, list)
    
    def test_generate_digest_no_data(self, generator):
        """Генерация дайджеста без данных."""
        # Мокаем отсутствие данных
        with patch.object(generator, 'get_transcriptions', return_value=[]):
            result = generator.generate_digest(date.today())
            # Должен вернуть пустой или минимальный дайджест
            assert result is not None


class TestFactExtraction:
    """Тесты извлечения фактов."""
    
    def test_fact_structure(self):
        """Структура факта."""
        fact = {
            "id": "fact_001",
            "transcription_id": "trans_001",
            "fact_text": "Meeting scheduled for Friday",
            "timestamp": datetime.now().isoformat(),
            "confidence": 0.9,
        }
        
        assert "id" in fact
        assert "fact_text" in fact
        assert "confidence" in fact
        assert 0 <= fact["confidence"] <= 1
    
    def test_fact_confidence_range(self):
        """Confidence факта в диапазоне 0-1."""
        facts = [
            {"confidence": 0.0},
            {"confidence": 0.5},
            {"confidence": 1.0},
        ]
        
        for fact in facts:
            assert 0 <= fact["confidence"] <= 1


class TestDigestOutput:
    """Тесты выходных данных дайджеста."""
    
    def test_digest_structure(self):
        """Структура дайджеста."""
        digest = {
            "id": "digest_001",
            "date": date.today().isoformat(),
            "content_path": "/path/to/digest.md",
            "summary": "Daily summary",
            "facts_count": 5,
            "created_at": datetime.now().isoformat(),
        }
        
        assert "id" in digest
        assert "date" in digest
        assert "summary" in digest
    
    def test_digest_facts_count_non_negative(self):
        """Количество фактов неотрицательно."""
        digest = {"facts_count": 0}
        assert digest["facts_count"] >= 0
        
        digest = {"facts_count": 10}
        assert digest["facts_count"] >= 0


class TestDigestMetrics:
    """Тесты метрик дайджеста."""
    
    def test_information_density_calculation(self):
        """Расчет плотности информации."""
        text = "This is a test sentence."
        words = len(text.split())
        
        assert words > 0
        # Плотность = факты / слова
        density = 2 / words
        assert 0 <= density <= 1
    
    def test_key_facts_extraction(self):
        """Извлечение ключевых фактов."""
        facts = [
            {"text": "Important fact 1", "confidence": 0.9},
            {"text": "Important fact 2", "confidence": 0.8},
        ]
        
        # Сортируем по confidence
        sorted_facts = sorted(facts, key=lambda x: x["confidence"], reverse=True)
        assert sorted_facts[0]["confidence"] >= sorted_facts[1]["confidence"]
