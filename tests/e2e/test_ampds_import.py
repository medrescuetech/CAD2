import io
import pytest
from tests.utils.http import login

@pytest.mark.e2e
@pytest.mark.ampds
def test_ampds_csv_import(app, client):
    # Login as admin
    status = login(client, 'admin', 'admin')
    assert status in (200, 302)

    # Set CSRF token directly in session to satisfy middleware
    token = 'test-csrf-token'
    with client.session_transaction() as sess:
        sess['csrf_token'] = token

    # Prepare a tiny AMPDS CSV in-memory
    csv_content = "unique_id,category,card_number,priority,subcategory\nA01,Medical,1,LOW,Abdominal Pain\n"
    data = {
        'file': (io.BytesIO(csv_content.encode('utf-8')), 'ampds_small.csv')
    }
    resp = client.post('/api/ampds/import', data=data, headers={'X-CSRF-Token': token}, content_type='multipart/form-data')
    # Should succeed or return structured error details
    assert resp.status_code in (200, 201)
    payload = resp.get_json()
    assert payload is not None
    # Expect success_count to be present
    assert 'success_count' in payload
