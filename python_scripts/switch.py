"""Spook - Your homie."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.const import EntityCategory

from ...entity import SpookEntityDescription
from .entity import CloudflaredSpookEntity  # Changed from HomeAssistantCloudSpookEntity

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback


@dataclass(frozen=True, kw_only=True)
class CloudflaredSpookSwitchEntityDescription(
    SpookEntityDescription,
    SwitchEntityDescription,
):
    """Class describing Spook Cloudflared switch entities."""

    is_on_fn: callable
    set_fn: callable


# 🚀 Define Cloudflared Switch (Only ON/OFF)
SWITCHES: tuple[CloudflaredSpookSwitchEntityDescription, ...] = (
    CloudflaredSpookSwitchEntityDescription(
        key="cloudflared_tunnel",
        entity_id="switch.cloudflared_tunnel",
        name="Cloudflared Tunnel",
        icon="mdi:cloud-lock",
        entity_category=EntityCategory.CONFIG,
        is_on_fn=lambda _: CloudflaredSpookSwitchEntity.get_tunnel_status(),
        set_fn=lambda _, enabled: None,  # No toggle functionality
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    _entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Spook Cloudflared switches."""
    async_add_entities(
        CloudflaredSpookSwitchEntity(description)
        for description in SWITCHES
    )


class CloudflaredSpookSwitchEntity(CloudflaredSpookEntity, SwitchEntity):
    """Spook switch providing Cloudflared monitoring."""

    entity_description: CloudflaredSpookSwitchEntityDescription

    @property
    def icon(self) -> str | None:
        """Return the icon."""
        if not self.is_on:
            return "mdi:cloud-alert"  # Show alert icon if the tunnel is down
        return "mdi:cloud-check"

    @property
    def is_on(self) -> bool:
        """Return the state of the switch (True = Tunnel is active)."""
        return self.get_tunnel_status()

    @staticmethod
    def get_tunnel_status() -> bool:
        """Check if Cloudflared tunnel is active."""
        try:
            result = subprocess.run(
                ["pgrep", "-f", "cloudflared"], capture_output=True, text=True
            )
            return result.returncode == 0  # Returns True if cloudflared is running
        except Exception:
            return False  # Assume tunnel is down if check fails
