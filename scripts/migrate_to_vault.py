#!/usr/bin/env python3
"""
Скрипт миграции secrets из .env в HashiCorp Vault.

Usage:
    python scripts/migrate_to_vault.py [--dry-run] [--env-file .env]

Options:
    --dry-run       Показать что будет сделано, но не выполнять
    --env-file      Путь к .env файлу (default: .env)
    --vault-addr    Адрес Vault (default: http://localhost:8200)
    --vault-token   Токен Vault (default: reflexio-dev-token)
"""

import argparse
import os
import sys
from pathlib import Path
from typing import Dict, Optional

# Добавляем src в путь
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.utils.logging import setup_logging, get_logger

setup_logging()
logger = get_logger("migrate_to_vault")


# Список secrets для миграции
SECRETS_MAP = {
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "supabase_service": "SUPABASE_SERVICE_KEY",
    "supabase_anon": "SUPABASE_ANON_KEY",
    "brave": "BRAVE_API_KEY",
    "brightdata": "BRIGHTDATA_API_KEY",
    "brightdata_proxy": "BRIGHTDATA_PROXY_HTTP",
}


def load_env_file(env_path: str) -> Dict[str, str]:
    """Загружает переменные из .env файла."""
    env_vars = {}
    
    if not os.path.exists(env_path):
        logger.error("env_file_not_found", path=env_path)
        return env_vars
    
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, value = line.split("=", 1)
                # Убираем кавычки если есть
                value = value.strip().strip('"').strip("'")
                env_vars[key] = value
    
    logger.info("env_file_loaded", path=env_path, vars_count=len(env_vars))
    return env_vars


def check_vault_connection(vault_addr: str, vault_token: str) -> bool:
    """Проверяет соединение с Vault."""
    try:
        import hvac
        client = hvac.Client(url=vault_addr, token=vault_token)
        
        if client.is_authenticated():
            logger.info("vault_connection_ok", addr=vault_addr)
            return True
        else:
            logger.error("vault_auth_failed")
            return False
    except ImportError:
        logger.error("hvac_not_installed", install_cmd="pip install hvac")
        return False
    except Exception as e:
        logger.error("vault_connection_error", error=str(e))
        return False


def migrate_secrets(
    env_vars: Dict[str, str],
    vault_addr: str,
    vault_token: str,
    dry_run: bool = False,
) -> bool:
    """
    Мигрирует secrets в Vault.
    
    Args:
        env_vars: Словарь переменных окружения
        vault_addr: Адрес Vault
        vault_token: Токен Vault
        dry_run: Если True, только показывает что будет сделано
        
    Returns:
        True если успешно
    """
    if not dry_run:
        try:
            import hvac
            client = hvac.Client(url=vault_addr, token=vault_token)
        except ImportError:
            logger.error("hvac_not_installed")
            return False
    
    migrated = 0
    skipped = 0
    failed = 0
    
    print("\n" + "="*60)
    print("MIGRATION PLAN")
    print("="*60)
    
    for vault_key, env_key in SECRETS_MAP.items():
        value = env_vars.get(env_key)
        
        if not value:
            print(f"⏭️  SKIP: {env_key} not found in .env")
            skipped += 1
            continue
        
        # Маскируем значение для вывода
        masked = value[:4] + "*" * (len(value) - 8) + value[-4:] if len(value) > 8 else "****"
        
        if dry_run:
            print(f"📋 WOULD MIGRATE: {env_key} → vault:{vault_key} = {masked}")
        else:
            try:
                secret_path = f"secret/data/reflexio/{vault_key}"
                client.secrets.kv.v2.create_or_update_secret(
                    path=secret_path,
                    secret={"value": value},
                    mount_point="secret",
                )
                print(f"✅ MIGRATED: {env_key} → vault:{vault_key}")
                migrated += 1
            except Exception as e:
                print(f"❌ FAILED: {env_key} → {str(e)}")
                failed += 1
    
    print("="*60)
    print(f"SUMMARY: {migrated} migrated, {skipped} skipped, {failed} failed")
    print("="*60)
    
    return failed == 0


def create_env_backup(env_path: str) -> Optional[str]:
    """Создает резервную копию .env файла."""
    from datetime import datetime
    
    backup_path = f"{env_path}.backup.{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    
    try:
        import shutil
        shutil.copy2(env_path, backup_path)
        logger.info("env_backup_created", path=backup_path)
        return backup_path
    except Exception as e:
        logger.error("backup_failed", error=str(e))
        return None


def sanitize_env_file(env_path: str, dry_run: bool = False):
    """Удаляет sensitive данные из .env (заменяет на [VAULT])."""
    if dry_run:
        print(f"\n📋 Would sanitize {env_path} (replace secrets with [VAULT])")
        return
    
    try:
        with open(env_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        
        sanitized = []
        for line in lines:
            stripped = line.strip()
            
            # Проверяем содержит ли строка API ключ
            is_secret = any(
                key in stripped for key in SECRETS_MAP.values()
            ) and "=" in stripped and not stripped.startswith("#")
            
            if is_secret:
                key = stripped.split("=")[0]
                sanitized.append(f"{key}=[VAULT]\n")
                print(f"🧹 SANITIZED: {key}")
            else:
                sanitized.append(line)
        
        # Создаем новый файл
        new_env_path = env_path + ".new"
        with open(new_env_path, "w", encoding="utf-8") as f:
            f.writelines(sanitized)
        
        # Заменяем старый файл
        os.replace(new_env_path, env_path)
        logger.info("env_sanitized", path=env_path)
        
    except Exception as e:
        logger.error("sanitize_failed", error=str(e))


def main():
    parser = argparse.ArgumentParser(
        description="Migrate secrets from .env to HashiCorp Vault"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without making changes",
    )
    parser.add_argument(
        "--env-file",
        default=".env",
        help="Path to .env file (default: .env)",
    )
    parser.add_argument(
        "--vault-addr",
        default="http://localhost:8200",
        help="Vault address (default: http://localhost:8200)",
    )
    parser.add_argument(
        "--vault-token",
        default="reflexio-dev-token",
        help="Vault token (default: reflexio-dev-token)",
    )
    parser.add_argument(
        "--sanitize",
        action="store_true",
        help="Remove secrets from .env after migration",
    )
    parser.add_argument(
        "--no-backup",
        action="store_true",
        help="Skip creating backup of .env",
    )
    
    args = parser.parse_args()
    
    print("\n" + "="*60)
    print("VAULT MIGRATION TOOL")
    print("="*60)
    print(f"Mode: {'DRY-RUN' if args.dry_run else 'LIVE'}")
    print(f"Env file: {args.env_file}")
    print(f"Vault: {args.vault_addr}")
    print("="*60 + "\n")
    
    # 1. Загружаем .env
    env_vars = load_env_file(args.env_file)
    if not env_vars:
        print("❌ No env variables loaded. Exiting.")
        return 1
    
    # 2. Проверяем Vault (если не dry-run)
    if not args.dry_run:
        if not check_vault_connection(args.vault_addr, args.vault_token):
            print("\n❌ Vault connection failed. Options:")
            print("   1. Start Vault: docker compose -f docker-compose.vault.yml up -d")
            print("   2. Use --dry-run to preview migration")
            print("   3. Check VAULT_ADDR and VAULT_TOKEN")
            return 1
        
        # Создаем бэкап
        if not args.no_backup:
            backup_path = create_env_backup(args.env_file)
            if backup_path:
                print(f"💾 Backup created: {backup_path}")
    
    # 3. Мигрируем
    success = migrate_secrets(
        env_vars,
        args.vault_addr,
        args.vault_token,
        dry_run=args.dry_run,
    )
    
    # 4. Санитизируем .env (опционально)
    if success and args.sanitize and not args.dry_run:
        print("\n" + "="*60)
        sanitize_env_file(args.env_file, dry_run=args.dry_run)
    
    # 5. Выводим инструкции
    print("\n" + "="*60)
    print("NEXT STEPS")
    print("="*60)
    
    if args.dry_run:
        print("To perform actual migration:")
        print("  1. Start Vault: docker compose -f docker-compose.vault.yml up -d")
        print("  2. Run without --dry-run:")
        print(f"     python {sys.argv[0]} --sanitize")
    else:
        print("Migration complete!")
        print("  1. Update your application to use Vault:")
        print("     VAULT_ENABLED=true")
        print("     VAULT_ADDR=http://localhost:8200")
        print("     VAULT_TOKEN=reflexio-dev-token")
        print("  2. Test: python -c \"from src.utils.vault_client import get_secret; print(get_secret('openai'))\"")
        print("  3. Remove .env.backup.* files when ready")
    
    print("="*60 + "\n")
    
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
