import asyncio
from typing import TYPE_CHECKING

import java
from pytale.events import on_async_event, on_event
from pytale.plugin import (
    ExecutionContext,
    PluginState,
    get_context,
    get_data_directory,
    get_identifier,
    get_manifest,
    get_state,
    on_setup,
    on_shutdown,
    on_start,
)

if TYPE_CHECKING:
    from java import JavaObject

_AddPlayerToWorldEvent = java.type(
    "com.hypixel.hytale.server.core.event.events.player.AddPlayerToWorldEvent"
)
_PlayerReadyEvent = java.type(
    "com.hypixel.hytale.server.core.event.events.player.PlayerReadyEvent"
)
_PlayerChatEvent = java.type(
    "com.hypixel.hytale.server.core.event.events.player.PlayerChatEvent"
)

print("=" * 60)
print("pyTale Plugin Information")
print("=" * 60)

identifier = get_identifier()
print(f"\nIdentifier:")
print(f"  Group: {identifier.group}")
print(f"  Name: {identifier.name}")

manifest = get_manifest()
print(f"\nManifest:")
print(f"  Name: {manifest.name}")
print(f"  Version: {manifest.version}")
print(f"  Description: {manifest.description}")
print(f"  Authors: {manifest.authors}")
print(f"  Website: {manifest.website}")

data_dir = get_data_directory()
print(f"\nData Directory: {data_dir}")

context = get_context()
print(f"\nExecution Context: {context.name} ({context.value})")

state = get_state()
ctx = get_context()
print(f"\nPlugin State (module import, ctx={ctx.name}): {state.name}")
if ctx == ExecutionContext.GENERAL:
    assert (
        state == PluginState.SETUP
    ), f"Expected SETUP at module import in GENERAL, got {state.name}"
else:
    assert (
        state == PluginState.ENABLED
    ), f"Expected ENABLED at module import in WORLD, got {state.name}"

print("\n" + "=" * 60)


@on_setup
def on_plugin_setup() -> None:
    state = get_state()
    print(f"[LIFECYCLE] Plugin setup! state={state.name}")
    assert state == PluginState.SETUP, f"Expected SETUP in @on_setup, got {state.name}"


@on_start
def on_plugin_start() -> None:
    state = get_state()
    print(f"[LIFECYCLE] Plugin started! state={state.name}")
    assert state == PluginState.START, f"Expected START in @on_start, got {state.name}"


@on_shutdown
def on_plugin_shutdown() -> None:
    state = get_state()
    print(f"[LIFECYCLE] Plugin shutting down! state={state.name}")
    assert (
        state == PluginState.SHUTDOWN
    ), f"Expected SHUTDOWN in @on_shutdown, got {state.name}"


@on_event(_AddPlayerToWorldEvent)
def handle_add_player_to_world(event: "JavaObject") -> None:
    print(
        f"[EVENT/off-WorldThread] AddPlayerToWorldEvent: world={event.getWorld().getName()}"
    )


@on_event(_PlayerReadyEvent)
def handle_player_ready(event: "JavaObject") -> None:
    state = get_state()
    print(
        f"[EVENT/WorldThread] PlayerReadyEvent: player={event.getPlayer().getUuid()} state={state.name}"
    )
    assert (
        state == PluginState.ENABLED
    ), f"Expected ENABLED in event handler, got {state.name}"


@on_async_event(_PlayerChatEvent)
async def handle_player_chat_async(event: "JavaObject") -> None:
    sender = event.getSender().getUsername()
    original = event.getContent()
    # Simulate async work (e.g. database lookup, moderation check).
    await asyncio.sleep(0.05)
    event.setContent(f"[async] {original}")
    print(
        f"[ASYNC-EVENT] PlayerChatEvent: {sender!r} said {original!r} → content prefixed"
    )
