#!/usr/bin/env sh
set -eu

DATA_DIR="${1:-data/ourairports}"
BASE_URL="https://davidmegginson.github.io/ourairports-data"

mkdir -p "$DATA_DIR"

curl -L "$BASE_URL/airports.csv" -o "$DATA_DIR/airports.csv"
curl -L "$BASE_URL/runways.csv" -o "$DATA_DIR/runways.csv"
curl -L "$BASE_URL/countries.csv" -o "$DATA_DIR/countries.csv"

printf 'Downloaded OurAirports CSV files to %s\n' "$DATA_DIR"
