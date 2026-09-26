#!/usr/bin/env bash
# Exit on error
set -o errexit

pip install -r requirements.txt
python manage.py migrate
python manage.py import_fuel_prices data/fuel-prices-for-be-assessment.csv
