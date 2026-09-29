"""Static info (system/software info) regression tests.

Some webOS 24/25 sets (seen on an LG UT91006LA, webOS TV 24 33.22.56)
answer getSystemInfo with ``401 insufficient permissions`` while every
other request works. bscpylgtv fetches its static states during connect
without error handling, so with ``system_info`` in the subscription set
every connect failed and the TV showed as off. The integration now keeps
the static states out of the library's set and fetches them itself, best
effort, after connecting.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from bscpylgtv.exceptions import PyLGTVCmdError
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant

from custom_components.bscpylgtv.const import DEFAULT_STATES, STATIC_INFO_STATES
from custom_components.bscpylgtv.coordinator import async_fetch_static_info

from .conftest import MockWebOsClient, TVSimulator, build_mock_config_entry

MEDIA_PLAYER = "media_player.lg_webos_tv_oled55c2"

_PERMISSION_ERROR = PyLGTVCmdError(
    {"type": "error", "id": 1, "error": "401 insufficient permissions"}
)


def test_static_states_not_subscribed_by_library() -> None:
    """The library never fetches the static states during connect."""
    for state in STATIC_INFO_STATES:
        assert state not in DEFAULT_STATES


async def test_fetch_static_info_tolerates_refused_request() -> None:
    """A refused getSystemInfo leaves system_info unset, software_info set."""
    software_info = {"product_name": "webOSTV 24", "major_ver": "33"}
    client = SimpleNamespace(
        _system_info=None,
        _software_info=None,
        get_system_info=AsyncMock(side_effect=_PERMISSION_ERROR),
        get_software_info=AsyncMock(return_value=software_info),
    )
    await async_fetch_static_info(client)  # type: ignore[arg-type]
    assert client._system_info is None  # noqa: SLF001
    assert client._software_info == software_info  # noqa: SLF001


async def test_setup_with_system_info_refused(
    hass: HomeAssistant, tv: TVSimulator
) -> None:
    """The entry loads and the TV shows as on when getSystemInfo is refused."""
    created: list[MockWebOsClient] = []

    def create(host: str, **kwargs: object) -> MockWebOsClient:
        client = tv.create_client(host, **kwargs)
        client.get_system_info = AsyncMock(  # type: ignore[method-assign]
            side_effect=_PERMISSION_ERROR
        )
        created.append(client)
        return client

    with patch(
        "custom_components.bscpylgtv.coordinator.WebOsClient", side_effect=create
    ):
        entry = build_mock_config_entry(hass, host=tv.host)
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED
    client = created[0]
    assert client.init_kwargs["states"] == DEFAULT_STATES
    client.get_system_info.assert_awaited()
    client.get_software_info.assert_awaited()
    assert entry.runtime_data.client.is_connected()
    assert hass.states.get(MEDIA_PLAYER).state == "on"
