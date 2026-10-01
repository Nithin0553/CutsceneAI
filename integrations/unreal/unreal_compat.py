"""Unreal-version compatibility shims for CutSceneAI's Sequencer adapter.

Every engine API incompatibility discovered during a real transfer should be fixed here
(or routed through here) and backed by a regression test plus the compatibility ledger.
"""

from __future__ import annotations

from typing import Any

import unreal


class UnrealCompatibilityError(RuntimeError):
    pass


def get_section_channels(section: Any) -> list[Any]:
    """Return Sequencer scripting channels across Unreal API variants.

    Unreal 5.8 exposes GetAllChannels through SequencerScripting. Older adapter code
    used get_channels(), which is not present on MovieScene3DTransformSection in 5.8.
    """
    get_all = getattr(section, "get_all_channels", None)
    if callable(get_all):
        return list(get_all())

    extensions = getattr(unreal, "MovieSceneSectionExtensions", None)
    extension_get_all = getattr(extensions, "get_all_channels", None) if extensions else None
    if callable(extension_get_all):
        return list(extension_get_all(section))

    legacy = getattr(section, "get_channels", None)
    if callable(legacy):
        return list(legacy())

    raise UnrealCompatibilityError(
        "Sequencer section exposes neither get_all_channels() nor a supported "
        "MovieSceneSectionExtensions.get_all_channels() fallback. Ensure the "
        "Sequencer Scripting plugin is enabled and use a supported Unreal version."
    )


def make_fixed_play_rate(rate: float) -> Any:
    """Create the play-rate representation required by Unreal 5.8."""
    variant_type = getattr(unreal, "MovieSceneTimeWarpVariant", None)
    if variant_type is None:
        # Compatibility fallback for older engines where play_rate accepted a float.
        return float(rate)

    variant = variant_type()
    setter = getattr(variant, "set_fixed_play_rate", None)
    if not callable(setter):
        raise UnrealCompatibilityError(
            "MovieSceneTimeWarpVariant exists but set_fixed_play_rate() is unavailable."
        )
    setter(float(rate))
    return variant
