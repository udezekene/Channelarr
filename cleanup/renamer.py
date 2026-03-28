"""Proposes channel renames by stripping region/country prefixes.

Takes existing channel names and applies the aggressive normalizer to produce
cleaner names (e.g. "SA|Rok" → "Rok", "MY|CNN" → "CNN"). Only proposes a
rename if the clean name doesn't already exist as another channel.
"""

from __future__ import annotations
from dataclasses import dataclass
from core.models import Channel
from core import normalizer as norm
from core.brands import apply_brands


@dataclass
class RenameProposal:
    channel: Channel
    current_name: str
    proposed_name: str


def find_renames(channels: list[Channel]) -> list[RenameProposal]:
    """Return rename proposals for channels whose aggressive-normalized name differs.

    Conflict check is scoped to the same channel_group_id — "CNN" in a UK group
    does not block renaming "UK-CNN" in a DSTV group to "CNN".
    """
    # Build a set of (group_id, lower_name) pairs for fast conflict lookup
    existing: set[tuple] = {(c.channel_group_id, c.name.lower()) for c in channels}
    proposals: list[RenameProposal] = []

    for channel in channels:
        proposed = apply_brands(norm.normalize(channel.name, "aggressive"))
        if not proposed or proposed == channel.name:
            continue
        # Block only if the proposed name already exists within the same group
        if (channel.channel_group_id, proposed.lower()) in existing:
            continue
        proposals.append(RenameProposal(
            channel=channel,
            current_name=channel.name,
            proposed_name=proposed,
        ))

    return proposals


def apply_renames(
    proposals: list[RenameProposal],
    client,
) -> tuple[list[RenameProposal], list[tuple[RenameProposal, str]]]:
    """Apply renames via the API client.

    Returns (succeeded, failed) where failed entries are (proposal, error_message).
    """
    succeeded: list[RenameProposal] = []
    failed: list[tuple[RenameProposal, str]] = []

    for proposal in proposals:
        try:
            payload = {**proposal.channel.raw, "name": proposal.proposed_name}
            client.update_channel(proposal.channel.id, payload)
            succeeded.append(proposal)
        except Exception as exc:
            failed.append((proposal, str(exc)))

    return succeeded, failed
