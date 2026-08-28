import pytest
from tests.utils.http import login, get

@pytest.mark.e2e
@pytest.mark.units
def test_units_page_access(app, client):
    status = login(client, 'admin', 'admin')
    assert status in (200, 302)
    units_status = get(client, '/units')
    assert units_status in (200, 302)
