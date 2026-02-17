"""
Тесты RLS (Row-Level Security) политик.
Reflexio 24/7 — November 2025 Integration Sprint
"""
import pytest
from pathlib import Path


def test_rls_migration_exists():
    """Проверяет наличие миграции RLS."""
    rls_migration = Path("src/storage/migrations/0003_rls_policies.sql")
    assert rls_migration.exists(), "RLS migration not found"


def test_rls_policies_defined():
    """Проверяет, что RLS политики определены для всех таблиц."""
    rls_migration = Path("src/storage/migrations/0003_rls_policies.sql")
    
    if rls_migration.exists():
        content = rls_migration.read_text(encoding="utf-8")
        
        # Таблицы, для которых должны быть RLS политики
        tables = [
            "audio_meta",
            "text_entries",
            "insights",
            "claims",
            "missions",
            "metrics",
        ]
        
        for table in tables:
            assert f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY" in content, \
                f"RLS not enabled for {table}"
            assert f'CREATE POLICY "allow read all" ON {table}' in content, \
                f"Read policy not found for {table}"


def test_user_preferences_rls():
    """Проверяет RLS для user_preferences."""
    migration = Path("src/storage/migrations/0004_user_preferences.sql")
    
    if migration.exists():
        content = migration.read_text(encoding="utf-8")
        assert "users_read_own_preferences" in content
        assert "users_update_own_preferences" in content
        assert "auth.uid()" in content, "RLS should use auth.uid() for user isolation"


def test_rls_activation_migration():
    """Проверяет миграцию активации RLS с tenant_id."""
    migration = Path("src/storage/migrations/0005_rls_activation.sql")
    
    if migration.exists():
        content = migration.read_text(encoding="utf-8")
        assert "tenant_id" in content, "Migration should add tenant_id column"
        assert "auth.uid()" in content, "RLS should use auth.uid() for tenant isolation"
        assert "users_read_own_data" in content, "Should have read policy with tenant_id"
        assert "users_write_own_data" in content, "Should have write policy with tenant_id"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

