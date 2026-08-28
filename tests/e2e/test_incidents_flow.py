import pytest
from tests.utils.http import login, get

@pytest.mark.e2e
@pytest.mark.incidents
def test_incidents_page_access(app, client):
    # Ensure we can log in and reach incidents page
    status = login(client, 'admin', 'admin')
    assert status in (200, 302)
    inc_status = get(client, '/incidents')
    # Page should be reachable for admin
    assert inc_status in (200, 302)
