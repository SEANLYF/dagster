import os
import shutil
import tempfile
from datetime import date
from functools import partial

from dagster_examples.bay_bikes.pipelines import generate_training_set, monthly_trip_pipeline
from numpy import array_equal
from pandas import DataFrame, Timestamp

from dagster import execute_pipeline, execute_pipeline_with_preset, seven

FAKE_ZIPFILE_NAME = 'data.csv.zip'


def environment_dictionary():
    return {
        'resources': {
            'postgres_db': {
                'config': {
                    'postgres_db_name': 'test',
                    'postgres_hostname': 'localhost',
                    'postgres_password': 'test',
                    'postgres_username': 'test',
                }
            },
            'volume': {'config': {'mount_location': ''}},
        },
        'solids': {
            'download_baybike_zipfile_from_url': {
                'inputs': {
                    'file_name': {'value': FAKE_ZIPFILE_NAME},
                    'base_url': {'value': 'https://foo.com'},
                }
            },
            'load_baybike_data_into_dataframe': {
                'inputs': {'target_csv_file_in_archive': {'value': '',}}
            },
            'insert_trip_data_into_table': {
                'config': {'index_label': 'uuid'},
                'inputs': {'table_name': 'test_trips'},
            },
        },
    }


FAKE_TRIP_DATA = [
    {
        'duration_sec': 68145,
        'start_time': '2019-08-31 21:27:42.2530',
        'end_time': '2019-09-01 16:23:27.4920',
        'start_station_id': 249,
        'start_station_name': 'Russell St at College Ave',
        'start_station_latitude': 37.8584732,
        'start_station_longitude': -122.2532529,
        'end_station_id': 247,
        'end_station_name': 'Fulton St at Bancroft Way',
        'end_station_latitude': 37.867789200000004,
        'end_station_longitude': -122.26589640000002,
        'bike_id': 3112,
        'user_type': 'Customer',
        'bike_share_for_all_trip': 'No',
    },
    {
        'duration_sec': 53216,
        'start_time': '2019-07-31 22:34:17.5120',
        'end_time': '2019-08-01 13:21:13.9310',
        'start_station_id': 368,
        'start_station_name': 'Myrtle St at Polk St',
        'start_station_latitude': 37.7854338279,
        'start_station_longitude': -122.41962164639999,
        'end_station_id': 78,
        'end_station_name': 'Folsom St at 9th St',
        'end_station_latitude': 37.7737172,
        'end_station_longitude': -122.41164669999999,
        'bike_id': 2440,
        'user_type': 'Customer',
        'bike_share_for_all_trip': 'No',
    },
]


FAKE_WEATHER_DATA = [
    {
        'time': 1567286562,
        'summary': 'Clear throughout the day.',
        'icon': 'clear-day',
        'sunriseTime': 1546269960,
        'sunsetTime': 1546304520,
        'moonPhase': 0.85,
        'precipIntensity': 0.0007,
        'precipIntensityMax': 0.0019,
        'precipIntensityMaxTime': 1546326000,
        'precipProbability': 0.05,
        'precipType': 'rain',
        'temperatureHigh': 56.71,
        'temperatureHighTime': 1546294020,
        'temperatureLow': 44.75,
        'temperatureLowTime': 1546358040,
        'apparentTemperatureHigh': 56.21,
        'apparentTemperatureHighTime': 1546294020,
        'apparentTemperatureLow': 41.33,
        'apparentTemperatureLowTime': 1546358040,
        'dewPoint': 28.34,
        'humidity': 0.43,
        'pressure': 1017.7,
        'windSpeed': 12.46,
        'windGust': 26.85,
        'windGustTime': 1546289220,
        'windBearing': 0,
        'cloudCover': 0.11,
        'uvIndex': 2,
        'uvIndexTime': 1546287180,
        'visibility': 10,
        'ozone': 314.4,
        'temperatureMin': 46.85,
        'temperatureMinTime': 1546263840,
        'temperatureMax': 56.71,
        'temperatureMaxTime': 1546294020,
        'apparentTemperatureMin': 43.54,
        'apparentTemperatureMinTime': 1546264740,
        'apparentTemperatureMax': 56.21,
        'apparentTemperatureMaxTime': 1546294020,
    },
    {
        'time': 1564612457,
        'summary': 'Clear throughout the day.',
        'icon': 'clear-day',
        'sunriseTime': 1546356420,
        'sunsetTime': 1546390920,
        'moonPhase': 0.88,
        'precipIntensity': 0.0005,
        'precipIntensityMax': 0.0016,
        'precipIntensityMaxTime': 1546370820,
        'precipProbability': 0.02,
        'precipType': 'sunny',
        'temperatureHigh': 55.91,
        'temperatureHighTime': 1546382040,
        'temperatureLow': 41.18,
        'temperatureLowTime': 1546437660,
        'apparentTemperatureHigh': 55.41,
        'apparentTemperatureHighTime': 1546382040,
        'apparentTemperatureLow': 38.76,
        'apparentTemperatureLowTime': 1546437600,
        'dewPoint': 20.95,
        'humidity': 0.33,
        'pressure': 1023.3,
        'windSpeed': 6.77,
        'windGust': 22.08,
        'windGustTime': 1546343340,
        'windBearing': 22,
        'cloudCover': 0.1,
        'uvIndex': 2,
        'uvIndexTime': 1546373580,
        'visibility': 10,
        'ozone': 305.3,
        'temperatureMin': 44.75,
        'temperatureMinTime': 1546358040,
        'temperatureMax': 55.91,
        'temperatureMaxTime': 1546382040,
        'apparentTemperatureMin': 41.33,
        'apparentTemperatureMinTime': 1546358040,
        'apparentTemperatureMax': 55.41,
        'apparentTemperatureMaxTime': 1546382040,
    },
]


def mock_download_zipfile(tmp_dir, fake_trip_data, _url, _target, _chunk_size):
    data_zip_file_path = os.path.join(tmp_dir, FAKE_ZIPFILE_NAME)
    DataFrame(fake_trip_data).to_csv(data_zip_file_path, compression='zip')


def test_monthly_trip_pipeline(mocker):
    env_dictionary = environment_dictionary()
    with seven.TemporaryDirectory() as tmp_dir:
        # Run pipeline
        download_zipfile = mocker.patch(
            'dagster_examples.bay_bikes.solids._download_zipfile_from_url',
            side_effect=partial(mock_download_zipfile, tmp_dir, FAKE_TRIP_DATA),
        )
        to_sql_call = mocker.patch('dagster_examples.bay_bikes.solids.DataFrame.to_sql')
        env_dictionary['resources']['volume']['config']['mount_location'] = tmp_dir
        # Done because we are zipping the file in the tmpdir
        env_dictionary['solids']['load_baybike_data_into_dataframe']['inputs'][
            'target_csv_file_in_archive'
        ]['value'] = os.path.join(tmp_dir, FAKE_ZIPFILE_NAME)
        result = execute_pipeline(monthly_trip_pipeline, environment_dict=env_dictionary)
        assert result.success
        download_zipfile.assert_called_with(
            'https://foo.com/data.csv.zip', os.path.join(tmp_dir, FAKE_ZIPFILE_NAME), 8192
        )
        to_sql_call.assert_called_with(
            'test_trips', mocker.ANY, if_exists='append', index=False, index_label='uuid'
        )


# pylint: disable=W0613
def mock_read_sql(table_name, _engine, index_col=None):
    if table_name == 'weather':
        return DataFrame(FAKE_WEATHER_DATA)
    elif table_name == 'trips':
        return DataFrame(FAKE_TRIP_DATA)
    return DataFrame()


def test_generate_training_set(mocker):
    mocker.patch('dagster_examples.bay_bikes.solids.read_sql_table', side_effect=mock_read_sql)

    # Execute Pipeline
    pipeline_result = execute_pipeline_with_preset(generate_training_set, preset_name='testing')
    assert pipeline_result.success

    # Check solids
    EXPECTED_TRAFFIC_RECORDS = [
        {
            'interval_date': date(2019, 7, 31),
            'peak_traffic_load': 1,
            'time': Timestamp('2019-07-31 00:00:00'),
        },
        {
            'interval_date': date(2019, 8, 31),
            'peak_traffic_load': 1,
            'time': Timestamp('2019-08-31 00:00:00'),
        },
    ]
    traffic_dataset = pipeline_result.output_for_solid(
        'transform_into_traffic_dataset', output_name='traffic_dataframe'
    ).to_dict('records')
    assert all(record in EXPECTED_TRAFFIC_RECORDS for record in traffic_dataset)

    EXPECTED_WEATHER_RECORDS = [
        {
            'time': Timestamp('2019-08-31 00:00:00'),
            'summary': 'Clear throughout the day.',
            'icon': 'clear-day',
            'sunriseTime': 1546269960,
            'sunsetTime': 1546304520,
            'precipIntensity': 0.0007,
            'precipIntensityMax': 0.0019,
            'precipProbability': 0.05,
            'temperatureHigh': 56.71,
            'temperatureHighTime': 1546294020,
            'temperatureLow': 44.75,
            'temperatureLowTime': 1546358040,
            'dewPoint': 28.34,
            'humidity': 0.43,
            'pressure': 1017.7,
            'windSpeed': 12.46,
            'windGust': 26.85,
            'windGustTime': 1546289220,
            'windBearing': 0,
            'cloudCover': 0.11,
            'uvIndex': 2,
            'uvIndexTime': 1546287180,
            'visibility': 10,
            'ozone': 314.4,
            'didRain': True,
        },
        {
            'time': Timestamp('2019-07-31 00:00:00'),
            'summary': 'Clear throughout the day.',
            'icon': 'clear-day',
            'sunriseTime': 1546356420,
            'sunsetTime': 1546390920,
            'precipIntensity': 0.0005,
            'precipIntensityMax': 0.0016,
            'precipProbability': 0.02,
            'temperatureHigh': 55.91,
            'temperatureHighTime': 1546382040,
            'temperatureLow': 41.18,
            'temperatureLowTime': 1546437660,
            'dewPoint': 20.95,
            'humidity': 0.33,
            'pressure': 1023.3,
            'windSpeed': 6.77,
            'windGust': 22.08,
            'windGustTime': 1546343340,
            'windBearing': 22,
            'cloudCover': 0.1,
            'uvIndex': 2,
            'uvIndexTime': 1546373580,
            'visibility': 10,
            'ozone': 305.3,
            'didRain': False,
        },
    ]
    weather_dataset = pipeline_result.output_for_solid(
        'produce_weather_dataset', output_name='weather_dataframe'
    ).to_dict('records')
    assert all(record in EXPECTED_WEATHER_RECORDS for record in weather_dataset)

    # Ensure we are generating the expected training set
    training_set, labels = pipeline_result.output_for_solid('produce_training_set')
    assert len(labels) == 1 and labels[0] == 1
    assert array_equal(
        training_set,
        [
            [
                [
                    1546356420.0,
                    1546390920.0,
                    0.0005,
                    0.0016,
                    0.02,
                    55.91,
                    1546382040.0,
                    41.18,
                    1546437660.0,
                    20.95,
                    0.33,
                    1023.3,
                    6.77,
                    22.08,
                    1546343340.0,
                    22.0,
                    0.1,
                    2.0,
                    1546373580.0,
                    10.0,
                    305.3,
                    1.0,
                    0.0,
                ],
                [
                    1546269960.0,
                    1546304520.0,
                    0.0007,
                    0.0019,
                    0.05,
                    56.71,
                    1546294020.0,
                    44.75,
                    1546358040.0,
                    28.34,
                    0.43,
                    1017.7,
                    12.46,
                    26.85,
                    1546289220.0,
                    0.0,
                    0.11,
                    2.0,
                    1546287180.0,
                    10.0,
                    314.4,
                    0.0,
                    1.0,
                ],
            ]
        ],
    )
    materialization_events = [
        event
        for event in pipeline_result.step_event_list
        if event.solid_name == 'upload_training_set_to_gcs'
        and event.event_type_value == 'STEP_MATERIALIZATION'
    ]
    assert len(materialization_events) == 1
    materialization = materialization_events[0].event_specific_data.materialization
    assert materialization.label == 'GCS Blob'
    materialization_event_metadata = materialization.metadata_entries
    assert len(materialization_event_metadata) == 1
    assert materialization_event_metadata[0].label == 'google cloud storage URI'
    assert materialization_event_metadata[0].entry_data.text.startswith(
        'gs://dagster-scratch-ccdfe1e/training_data'
    )

    # Clean up
    shutil.rmtree(os.path.join(tempfile.gettempdir(), 'testing-storage'), ignore_errors=True)
