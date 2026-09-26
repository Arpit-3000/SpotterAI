import tempfile
import pytest
from decimal import Decimal
from pathlib import Path
from django.core.management import call_command, CommandError
from fuel_optimizer.models import FuelStation


@pytest.mark.django_db
class TestImportFuelPricesCommand:
    def test_import_valid_csv(self):
        csv_data = (
            "OPIS Truckstop ID,Truckstop Name,Address,City,State,Rack ID,Retail Price\n"
            "501,TEST TRAVEL PLAZA,100 HIGHWAY 1,Austin,TX,10,3.159\n"
            "502,SPEEDY STOP,200 HIGHWAY 2,Dallas,TX,11,3.299\n"
        )
        with tempfile.NamedTemporaryFile('w', suffix='.csv', delete=False, encoding='utf-8') as tf:
            tf.write(csv_data)
            tf_path = tf.name

        try:
            call_command('import_fuel_prices', tf_path, '--wipe')
            assert FuelStation.objects.count() == 2

            st = FuelStation.objects.get(opis_id=501)
            assert st.name == "TEST TRAVEL PLAZA"
            assert st.city == "Austin"
            assert st.state == "TX"
            assert st.retail_price == Decimal("3.1590")
        finally:
            Path(tf_path).unlink(missing_ok=True)

    def test_import_missing_columns_raises_error(self):
        bad_csv = (
            "Wrong Column,Name,Price\n"
            "1,Test,3.50\n"
        )
        with tempfile.NamedTemporaryFile('w', suffix='.csv', delete=False, encoding='utf-8') as tf:
            tf.write(bad_csv)
            tf_path = tf.name

        try:
            with pytest.raises(CommandError) as exc_info:
                call_command('import_fuel_prices', tf_path)
            assert "missing required columns" in str(exc_info.value)
        finally:
            Path(tf_path).unlink(missing_ok=True)

    def test_import_is_idempotent(self):
        csv_data = (
            "OPIS Truckstop ID,Truckstop Name,Address,City,State,Rack ID,Retail Price\n"
            "701,IDEMPOTENT STOP,300 HIGHWAY 3,Houston,TX,12,3.100\n"
        )
        with tempfile.NamedTemporaryFile('w', suffix='.csv', delete=False, encoding='utf-8') as tf:
            tf.write(csv_data)
            tf_path = tf.name

        try:
            call_command('import_fuel_prices', tf_path, '--wipe')
            assert FuelStation.objects.count() == 1

            # Run again without wipe
            call_command('import_fuel_prices', tf_path)
            assert FuelStation.objects.count() == 1
        finally:
            Path(tf_path).unlink(missing_ok=True)
