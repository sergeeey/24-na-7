"""
Тесты миграций Supabase + RLS.
Reflexio 24/7 — November 2025 Integration Sprint
"""
import pytest
from pathlib import Path

from src.storage.migrate import apply_schema_migrations


def test_migrations_exist():
    """Проверяет, что все миграции существуют."""
    migrations_dir = Path("src/storage/migrations")
    
    expected_migrations = [
        "0001_init.sql",
        "0002_indexes.sql",
        "0003_rls_policies.sql",
        "0004_user_preferences.sql",
        "0005_rls_activation.sql",
        "0006_billing.sql",
        "0007_referrals.sql",
    ]
    
    for migration in expected_migrations:
        migration_path = migrations_dir / migration
        assert migration_path.exists(), f"Migration {migration} not found"


def test_migration_syntax():
    """Проверяет синтаксис SQL миграций."""
    migrations_dir = Path("src/storage/migrations")
    
    for migration_file in migrations_dir.glob("*.sql"):
        content = migration_file.read_text(encoding="utf-8")
        
        # Базовая проверка синтаксиса
        assert "CREATE TABLE" in content or "ALTER TABLE" in content or "CREATE INDEX" in content, \
            f"Migration {migration_file.name} seems invalid"


def test_rls_policies():
    """Проверяет наличие RLS политик."""
    rls_migration = Path("src/storage/migrations/0003_rls_policies.sql")
    
    if rls_migration.exists():
        content = rls_migration.read_text(encoding="utf-8")
        assert "ENABLE ROW LEVEL SECURITY" in content
        assert "CREATE POLICY" in content


def test_user_preferences_migration():
    """Проверяет миграцию user_preferences."""
    migration = Path("src/storage/migrations/0004_user_preferences.sql")
    
    if migration.exists():
        content = migration.read_text(encoding="utf-8")
        assert "user_preferences" in content
        assert "opt_out_training" in content
        assert "RLS" in content or "ROW LEVEL SECURITY" in content


@pytest.mark.skipif(
    not Path(".env").exists() or "SUPABASE_URL" not in open(".env").read(),
    reason="Supabase not configured"
)
def test_migration_apply():
    """Тест применения миграций (требует Supabase)."""
    result = apply_schema_migrations(backend="supabase")
    
    assert "migrations_applied" in result
    assert len(result.get("errors", [])) == 0, f"Migration errors: {result.get('errors')}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

