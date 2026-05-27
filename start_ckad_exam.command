#!/bin/bash
set -euo pipefail

cd "$(dirname "$0")"

if [ ! -d .venv ]; then
  python3 -m venv .venv
fi

source .venv/bin/activate
python -m pip install --quiet --upgrade pip
python -m pip install --quiet -e .

clear
printf 'Starting CKAD interactive exam...\n\n'
ckad-drills run --mode exam --namespace drill-01

printf '\nPress ENTER to close this window...'
read -r
