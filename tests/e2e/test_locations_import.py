import io
import pytest
from tests.utils.http import login

@pytest.mark.e2e
@pytest.mark.locations
def test_locations_csv_import(app, client):
    # Login as admin
    status = login(client, 'admin', 'admin')
    assert status in (200, 302)

    # Prepare a small Locations CSV in-memory (matches blueprint expectations)
    csv_content = (
        "name,latitude,longitude\n"
        "Main Street,-20.7256,116.8464\n"
        "Harbor Point,-20.7300,116.8500\n"
    )
    data = {
        'file': (io.BytesIO(csv_content.encode('utf-8')), 'locations_small.csv')
    }

    resp = client.post('/locations/import', data=data, content_type='multipart/form-data')
    assert resp.status_code in (200, 201)
    payload = resp.get_json()
    assert payload is not None
    assert payload.get('success') is True
    assert payload.get('imported_count', 0) >= 1
