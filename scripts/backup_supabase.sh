#!/bin/bash
# Backup Supabase database snapshot
# Creates a backup with timestamp

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_NAME="reflexio_prod_${TIMESTAMP}"

echo "Creating Supabase backup: ${BACKUP_NAME}"

# Проверяем что Supabase CLI доступен
if command -v supabase &> /dev/null; then
    echo "Using Supabase CLI for backup..."
    supabase db dump -f "${BACKUP_NAME}.sql" || echo "⚠️  Supabase CLI backup failed"
else
    echo "⚠️  Supabase CLI not found. Manual backup required:"
    echo "   1. Go to Supabase Dashboard → Database → Backups"
    echo "   2. Create manual backup"
    echo "   3. Name: ${BACKUP_NAME}"
fi

echo "✅ Backup process initiated: ${BACKUP_NAME}"











