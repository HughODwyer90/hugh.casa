"""Spook - Your homie."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.helpers.device_registry import DeviceInfo

from ...const import DOMAIN
from ...entity import SpookEntity, SpookEntityDescription

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

class CloudflaredSpookEntity(SpookEntity):
    """Defines a base Spook entity for Cloudflared-related entities."""

    def __init__(self, description: SpookEntityDescription) -> None:
        """Initialize the entity."""
        super().__init__(description=description)

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, "cloudflared")},  # Unique identifier
            manufacturer="Cloudflare Inc.",
            name="Cloudflared Tunnel",
            configuration_url="https://dash.cloudflare.com/",
        )
        self._attr_unique_id = f"cloudflared_{description.key}"

    @property
    def available(self) -> bool:
        """Return if Cloudflared services are available."""
        return super().available  # No cloud login check required
