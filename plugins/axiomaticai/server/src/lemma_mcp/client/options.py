"""What the signed-in user can choose for a conversation: models and machines."""

from typing import Any

from . import LemmaClient


async def models(client: LemmaClient) -> list[dict[str, Any]]:
    """Each provider the user can run on, with the model tiers they can pick on it."""
    return (await client.request("GET", "/users/me/available-model-families")).json()


async def workflows(client: LemmaClient) -> list[dict[str, Any]]:
    """The ready-made workflows, each with the inputs it asks for."""
    return (await client.request("GET", "/workflows")).json()


async def machines(client: LemmaClient) -> list[dict[str, Any]]:
    """The machines a conversation can start on, with their size and cost."""
    return (await client.request("GET", "/users/me/available-sandbox-types")).json()
