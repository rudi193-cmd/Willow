#!/bin/bash
# Sync Willow repo to Google Drive (excluding sensitive and heavy files)
# Usage: bash sync_to_drive.sh

SRC="/mnt/c/Users/Sean/Documents/GitHub/willow-1.4/"
DST="/mnt/c/Users/Sean/My Drive (rudi193@gmail.com)/Willow/"

rsync -av --delete \
  --exclude='.git/' \
  --exclude='*.db' \
  --exclude='*.db-shm' \
  --exclude='*.db-wal' \
  --exclude='*.db-journal' \
  --exclude='artifacts/' \
  --exclude='ui/node_modules/' \
  --exclude='ui/dist/' \
  --exclude='__pycache__/' \
  --exclude='*.pyc' \
  --exclude='logs/' \
  --exclude='*.log' \
  --exclude='credentials.json' \
  --exclude='keys/' \
  --exclude='.env' \
  --exclude='*.pid' \
  --exclude='shiva_memory/*.db' \
  --exclude='temp/' \
  --exclude='*.exe' \
  --exclude='nul' \
  "$SRC" "$DST"

echo "Sync complete."
