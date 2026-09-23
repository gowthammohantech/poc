"""A mailbox connection carries the regime its attachments are processed under.

Before this, everything a connector pulled was filed as INDIA, so a mailbox
feeding the US pipeline produced documents the US documents list never showed.
The country now lives on the connection: chosen when it is connected, editable
afterwards, and read by every sync.
"""

import uuid

import pytest
from pymongo.errors import WriteError

from app.services import connector_service


class TestConnectionCountry:
    """What the sync reads off a connection record."""

    def test_a_record_without_a_country_is_india(self):
        """Connections made before the field existed carry nothing."""
        assert connector_service.connection_country({"country": None}) == "INDIA"
        assert connector_service.connection_country({}) == "INDIA"

    def test_case_is_normalised(self):
        assert connector_service.connection_country({"country": "usa"}) == "USA"

    def test_an_unknown_country_falls_back_to_india(self):
        """Neither pipeline would run for a value outside the two regimes."""
        assert connector_service.connection_country({"country": "CANADA"}) == "INDIA"


async def test_connecting_stores_the_chosen_country(mongo_db):
    """The regime the user is working in is fixed onto the pending connection."""
    connection_id, _url = await connector_service.begin_oauth("FAKE", country="USA")
    connection = await connector_service.get_connection(connection_id)

    assert connector_service.connection_country(connection) == "USA"


async def test_connecting_without_a_country_is_india(mongo_db):
    connection_id, _url = await connector_service.begin_oauth("FAKE")
    connection = await connector_service.get_connection(connection_id)

    assert connector_service.connection_country(connection) == "INDIA"


async def test_a_new_connection_carries_every_field(mongo_db):
    """The connectors page reads these by name, so none may be absent."""
    connection_id, _url = await connector_service.begin_oauth("FAKE")
    connection = await connector_service.get_connection(connection_id)

    for field in connector_service._CONNECTION_DEFAULTS:
        assert field in connection, field
    assert connection["filter_query"] == "has:attachment"


async def test_the_country_is_normalised_on_update(mongo_db):
    """The filters form posts whatever the select holds; junk must not stick."""
    connection_id, _url = await connector_service.begin_oauth("FAKE")

    await connector_service.update_connection(connection_id, country="usa")
    assert connector_service.connection_country(
        await connector_service.get_connection(connection_id)
    ) == "USA"

    await connector_service.update_connection(connection_id, country="ATLANTIS")
    assert connector_service.connection_country(
        await connector_service.get_connection(connection_id)
    ) == "INDIA"


async def test_a_connection_cannot_be_stored_with_a_country_outside_the_regimes(mongo_db):
    """update_connection normalises, so this is the backstop under it."""
    with pytest.raises(WriteError):
        await mongo_db.connector_connections.insert_one({
            "_id": str(uuid.uuid4()), "provider": "GMAIL",
            "status": "PENDING", "country": "ATLANTIS",
        })
