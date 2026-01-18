#!/bin/bash
# Copy local SQLite DB into OneDrive backup folder.
# Adjust paths for your environment.

SOURCE_DB="$HOME/vi_portfolio/db/vi_portfolio.db"
TARGET_DB="$HOME/OneDrive/vi_backups/vi_portfolio.db"

mkdir -p "$(dirname "$TARGET_DB")"
cp "$SOURCE_DB" "$TARGET_DB"
echo "Backup completed at $(date) -> $TARGET_DB"
