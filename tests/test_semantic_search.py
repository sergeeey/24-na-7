"""
Тесты для semantic search в embeddings.py.

Проверяет гибридный поиск (cosine + lexical), _cosine(), и edge cases.
"""
import json
from unittest.mock import patch, MagicMock

import pytest

from src.storage.embeddings import _cosine, search_phrases


class TestCosine:
    """Unit tests для _cosine() — cosine similarity."""

    def test_identical_vectors(self):
        """Одинаковые вектора → 1.0."""
        assert _cosine([1, 0, 0], [1, 0, 0]) == pytest.approx(1.0)

    def test_orthogonal_vectors(self):
        """Ортогональные вектора → 0.0."""
        assert _cosine([1, 0], [0, 1]) == pytest.approx(0.0)

    def test_opposite_vectors(self):
        """Противоположные вектора → -1.0."""
        assert _cosine([1, 0], [-1, 0]) == pytest.approx(-1.0)

    def test_empty_vectors(self):
        """Пустые вектора → 0.0 (без crash)."""
        assert _cosine([], []) == 0.0
        assert _cosine([1, 2], []) == 0.0
        assert _cosine([], [1, 2]) == 0.0

    def test_different_lengths(self):
        """Разная длина → берёт min(len(a), len(b))."""
        # [1,0] vs [1,0] (первые 2 элемента) → 1.0
        assert _cosine([1, 0], [1, 0, 999]) == pytest.approx(1.0)


class TestSearchPhrasesSemantic:
    """Тесты для search_phrases() с гибридным поиском."""

    @pytest.fixture
    def mock_db(self):
        """Фейковый db_backend, возвращающий записи из text_entries."""
        db = MagicMock()
        return db

    @patch("src.storage.embeddings._ensure_text_entries_table")
    @patch("src.storage.embeddings.generate_embeddings")
    def test_search_semantic_match(self, mock_gen_emb, mock_ensure, mock_db):
        """'тревога' находит 'беспокойство' через embedding similarity.

        ПОЧЕМУ этот тест важен: старая реализация делала query.lower() in text.lower(),
        т.е. 'тревога' НЕ находила 'беспокойство'. Новая — через cosine similarity.
        """
        # Мокаем: query embedding = [1, 0, 0]
        mock_gen_emb.return_value = [1.0, 0.0, 0.0]

        # Записи в БД: 'беспокойство' имеет похожий embedding [0.9, 0.1, 0.0]
        mock_db.select.return_value = [
            {
                "content": "Я испытываю беспокойство",
                "embedding": json.dumps([0.9, 0.1, 0.0]),
                "metadata": json.dumps({"start_time": 1.0, "end_time": 2.0, "confidence": 0.95}),
            },
            {
                "content": "Погода сегодня хорошая",
                "embedding": json.dumps([0.0, 0.0, 1.0]),
                "metadata": json.dumps({"start_time": 3.0, "end_time": 4.0, "confidence": 0.8}),
            },
        ]

        results = search_phrases("тревога", db_backend=mock_db)

        assert len(results) == 2
        # 'беспокойство' должен быть первым (высокий cosine similarity)
        assert results[0]["text"] == "Я испытываю беспокойство"
        assert results[0]["score"] > results[1]["score"]
        assert results[0]["start"] == 1.0
        assert results[0]["confidence"] == 0.95

    @patch("src.storage.embeddings._ensure_text_entries_table")
    @patch("src.storage.embeddings.generate_embeddings")
    def test_search_lexical_fallback(self, mock_gen_emb, mock_ensure, mock_db):
        """Точное совпадение ранжируется высоко даже при нулевом embedding.

        ПОЧЕМУ: если embeddings сломаны (fallback hash), lexical часть формулы
        (0.3 * 1.0 = 0.3) всё равно подтянет точные совпадения наверх.
        """
        # Все embeddings нулевые (сломанный провайдер)
        mock_gen_emb.return_value = [0.0, 0.0, 0.0]

        mock_db.select.return_value = [
            {
                "content": "Я чувствую тревогу и страх",
                "embedding": json.dumps([0.0, 0.0, 0.0]),
                "metadata": json.dumps({"start_time": 5.0, "end_time": 6.0, "confidence": 0.9}),
            },
            {
                "content": "Погода прекрасная",
                "embedding": json.dumps([0.0, 0.0, 0.0]),
                "metadata": json.dumps({"start_time": 7.0, "end_time": 8.0, "confidence": 0.85}),
            },
        ]

        results = search_phrases("тревогу", db_backend=mock_db)

        assert len(results) == 2
        # Точное совпадение 'тревогу' в тексте → lexical=1.0 → score=0.3
        assert results[0]["text"] == "Я чувствую тревогу и страх"
        assert results[0]["score"] == 0.3
        # Нет совпадения → score=0.0
        assert results[1]["score"] == 0.0

    @patch("src.storage.embeddings._ensure_text_entries_table")
    @patch("src.storage.embeddings.generate_embeddings")
    def test_search_empty_table(self, mock_gen_emb, mock_ensure, mock_db):
        """Пустая таблица → пустой результат (без crash)."""
        mock_gen_emb.return_value = [1.0, 0.0]
        mock_db.select.return_value = []

        results = search_phrases("что угодно", db_backend=mock_db)

        assert results == []

    @patch("src.storage.embeddings._ensure_text_entries_table")
    @patch("src.storage.embeddings.generate_embeddings")
    def test_search_metadata_parsing(self, mock_gen_emb, mock_ensure, mock_db):
        """metadata как dict (Supabase) и как string (SQLite) оба парсятся."""
        mock_gen_emb.return_value = [1.0, 0.0]

        mock_db.select.return_value = [
            {
                "content": "тест с dict metadata",
                "embedding": [1.0, 0.0],  # уже list (Supabase)
                "metadata": {"start_time": 10.0, "end_time": 11.0, "confidence": 0.99},
            },
            {
                "content": "тест с string metadata",
                "embedding": json.dumps([1.0, 0.0]),  # JSON string (SQLite)
                "metadata": json.dumps({"start_time": 20.0, "end_time": 21.0, "confidence": 0.88}),
            },
        ]

        results = search_phrases("тест", db_backend=mock_db)

        assert len(results) == 2
        # Оба должны корректно парсить metadata
        starts = {r["start"] for r in results}
        assert 10.0 in starts
        assert 20.0 in starts
