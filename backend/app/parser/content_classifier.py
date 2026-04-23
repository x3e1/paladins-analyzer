"""Content-first classifier for Paladins config files.

We do not trust filenames. Every uploaded document is parsed, then scored
against section fingerprints for each of the six supported Paladins file
types. Filenames are only consulted as a tiebreaker when scores are equal
and both non-zero — they never reject valid content.

Outcomes:
  - one of the six supported types (``ChaosEngine``, ``ChaosGame``, ...).
  - ``Fragment`` — one signature hit but no required section. Rule-only
    analysis, no cross-file / patch work.
  - ``Mixed`` — required sections from >= 2 supported types appear in the
    same document. Rejected in v1; user must split.
  - ``Unsupported`` — doesn't match anything, or is empty/comment-only.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .ue3_ini import ParsedDoc

SupportedType = Literal[
    "ChaosEngine",
    "ChaosGame",
    "ChaosInput",
    "ChaosLightmass",
    "ChaosSystemSettings",
    "ChaosUI",
]

ClassifiedType = Literal[
    "ChaosEngine",
    "ChaosGame",
    "ChaosInput",
    "ChaosLightmass",
    "ChaosSystemSettings",
    "ChaosUI",
    "Fragment",
    "Mixed",
    "Unsupported",
]

SUPPORTED_TYPES: tuple[SupportedType, ...] = (
    "ChaosEngine",
    "ChaosGame",
    "ChaosInput",
    "ChaosLightmass",
    "ChaosSystemSettings",
    "ChaosUI",
)


@dataclass(frozen=True)
class Fingerprint:
    """Fingerprint for identifying a Paladins file type by content."""

    # Any one of these sections is a strong positive signal.
    required_sections: frozenset[str]
    # Characteristic keys in specific sections (section -> keys).
    signature_keys: dict[str, frozenset[str]]
    # Sections whose presence downweights this type.
    negative_sections: frozenset[str]
    # Canonical filename used as the sole tiebreaker.
    canonical_filename: str


# Fingerprints are derived from general UE3 conventions plus section/key names
# seen in Paladins-adjacent configs. Each entry is an explicit, auditable
# hypothesis — not a guarantee. Entries are narrow enough to avoid collisions
# between types in typical files. Foreign sections in a classified file are
# reported as ``skipped_sections`` rather than silently treated as signal.
FINGERPRINTS: dict[SupportedType, Fingerprint] = {
    "ChaosEngine": Fingerprint(
        required_sections=frozenset(
            {
                "Engine.Engine",
                "Engine.GameEngine",
                "Core.System",
            }
        ),
        signature_keys={
            # Signature keys must be verified present in clean install.
            # bUseVSync and OneFrameThreadLag were removed — clean install
            # showed them absent from [Engine.Engine] (they live under
            # ChaosSystemSettings/[SystemSettings] as UseVsync and
            # OneFrameThreadLag respectively).
            "Engine.Engine": frozenset(
                {
                    "bSmoothFrameRate",
                    "MaxSmoothedFrameRate",
                    "MinSmoothedFrameRate",
                    "bUseTextureStreaming",
                }
            ),
            "TextureStreaming": frozenset({"PoolSize", "MemoryMargin"}),
        },
        negative_sections=frozenset({"DevOptions.StaticLighting"}),
        canonical_filename="ChaosEngine.ini",
    ),
    "ChaosGame": Fingerprint(
        required_sections=frozenset(
            {
                "Engine.GameInfo",
                "Engine.PlayerController",
                "Engine.WorldInfo",
            }
        ),
        signature_keys={
            "Engine.GameInfo": frozenset({"GameDifficulty", "MaxPlayers"}),
        },
        negative_sections=frozenset({"DevOptions.StaticLighting", "UIEditor.Generic"}),
        canonical_filename="ChaosGame.ini",
    ),
    "ChaosInput": Fingerprint(
        required_sections=frozenset(
            {
                "Engine.PlayerInput",
                "Engine.Console",
            }
        ),
        signature_keys={
            "Engine.PlayerInput": frozenset(
                {
                    "bEnableMouseSmoothing",
                    "MouseSensitivity",
                    "Bindings",
                }
            ),
        },
        negative_sections=frozenset({"SystemSettings"}),
        canonical_filename="ChaosInput.ini",
    ),
    "ChaosLightmass": Fingerprint(
        required_sections=frozenset(
            {
                "DevOptions.StaticLighting",
                "DevOptions.StaticLightingSceneConstants",
                "DevOptions.StaticShadows",
            }
        ),
        signature_keys={
            "DevOptions.StaticLighting": frozenset({"bAllowMultiThreadedStaticLighting"}),
        },
        negative_sections=frozenset({"SystemSettings", "Engine.PlayerInput"}),
        canonical_filename="ChaosLightmass.ini",
    ),
    "ChaosSystemSettings": Fingerprint(
        # Real clean install has [SystemSettings] plus 5 numbered
        # SystemSettingsBucket* sections (1..5), not 'HighEnd'/'LowEnd'.
        required_sections=frozenset(
            {
                "SystemSettings",
                "SystemSettingsBucket1",
                "SystemSettingsBucket2",
                "SystemSettingsBucket3",
            }
        ),
        signature_keys={
            "SystemSettings": frozenset(
                {
                    "MaxAnisotropy",
                    "DetailMode",
                    "MaxShadowResolution",
                    "MotionBlur",
                    "Bloom",
                    "OneFrameThreadLag",
                    "UseVsync",
                    "TexturePoolSize",
                }
            ),
        },
        negative_sections=frozenset({"Engine.PlayerInput", "DevOptions.StaticLighting"}),
        canonical_filename="ChaosSystemSettings.ini",
    ),
    "ChaosUI": Fingerprint(
        # Clean install ChaosUI has only Engine.UIInteraction,
        # Engine.GameUISceneClient, GFxUI.GFxMoviePlayer, Configuration,
        # and IniVersion. The earlier hypothesis (UIEditor.*, FullScreenMovie)
        # was wrong for Paladins.
        required_sections=frozenset(
            {
                "Engine.UIInteraction",
                "Engine.GameUISceneClient",
                "GFxUI.GFxMoviePlayer",
            }
        ),
        signature_keys={
            "Engine.UIInteraction": frozenset(
                {
                    "UIAxisMultiplier",
                    "UIJoystickDeadZone",
                    "DoubleClickPixelTolerance",
                }
            ),
            "Engine.GameUISceneClient": frozenset(
                {
                    "bRenderDebugInfo",
                    "bCaptureUnprocessedInput",
                }
            ),
        },
        negative_sections=frozenset({"SystemSettings", "DevOptions.StaticLighting"}),
        canonical_filename="ChaosUI.ini",
    ),
}


@dataclass(frozen=True)
class ClassificationResult:
    classified_type: ClassifiedType
    score: float
    # Scores for all types (useful for reporting and debugging).
    per_type_scores: dict[SupportedType, float]
    # Sections in the doc that did not contribute to the winning type's
    # signal — surfaced to the user as ``skipped_sections``.
    foreign_sections: list[str]
    # When classified as Mixed, the types that tied or co-dominate.
    mixed_types: tuple[SupportedType, ...] = ()


MIN_SCORE_FOR_TYPE = 1.0
MIN_REQUIRED_FOR_TYPE = 1  # must have >=1 required_section match
FRAGMENT_SIGNATURE_MIN = 1  # a fragment has at least one signature key
AMBIGUITY_MARGIN = 0.0  # equal scores -> ambiguous


def _score_against(fp: Fingerprint, doc_sections: dict[str, list]) -> tuple[float, int, int]:
    """Return (score, required_hits, signature_hits) for a fingerprint."""
    present = set(doc_sections.keys())
    required_hits = len(fp.required_sections & present)
    # Score is weighted: required_section hit = 2, signature_key hit = 1,
    # negative_section presence = -2.
    score = 2.0 * required_hits

    signature_hits = 0
    for section, keys in fp.signature_keys.items():
        entries = doc_sections.get(section, [])
        entry_keys = {e.key for e in entries}
        matched = keys & entry_keys
        signature_hits += len(matched)
        score += 1.0 * len(matched)

    for neg in fp.negative_sections:
        if neg in present:
            score -= 2.0
    return score, required_hits, signature_hits


def classify(doc: ParsedDoc) -> ClassificationResult:
    """Classify a parsed document against the six Paladins fingerprints."""
    per_type_scores: dict[SupportedType, float] = {}
    per_type_required: dict[SupportedType, int] = {}
    per_type_signature: dict[SupportedType, int] = {}

    for t, fp in FINGERPRINTS.items():
        score, required_hits, signature_hits = _score_against(fp, doc.sections)
        per_type_scores[t] = score
        per_type_required[t] = required_hits
        per_type_signature[t] = signature_hits

    # Primary: types with >=1 required_section hit and a positive score.
    primary_candidates = [
        t
        for t in SUPPORTED_TYPES
        if per_type_required[t] >= MIN_REQUIRED_FOR_TYPE and per_type_scores[t] >= MIN_SCORE_FOR_TYPE
    ]

    if len(primary_candidates) >= 2:
        # Mixed — required sections from two+ supported types coexist.
        return ClassificationResult(
            classified_type="Mixed",
            score=max(per_type_scores[t] for t in primary_candidates),
            per_type_scores=per_type_scores,
            foreign_sections=[],
            mixed_types=tuple(primary_candidates),
        )

    if len(primary_candidates) == 1:
        winner = primary_candidates[0]
        foreign = _foreign_sections_for(winner, doc.sections)
        return ClassificationResult(
            classified_type=winner,
            score=per_type_scores[winner],
            per_type_scores=per_type_scores,
            foreign_sections=foreign,
        )

    # No primary candidate. Check for a signature-only hit (Fragment).
    fragment_candidates = [
        t for t in SUPPORTED_TYPES if per_type_signature[t] >= FRAGMENT_SIGNATURE_MIN
    ]
    if len(fragment_candidates) == 1:
        return ClassificationResult(
            classified_type="Fragment",
            score=per_type_scores[fragment_candidates[0]],
            per_type_scores=per_type_scores,
            foreign_sections=[],
            mixed_types=(fragment_candidates[0],),
        )
    if len(fragment_candidates) >= 2:
        # Fragment spanning multiple types -> ambiguous; reject as Unsupported.
        return ClassificationResult(
            classified_type="Unsupported",
            score=0.0,
            per_type_scores=per_type_scores,
            foreign_sections=[],
        )

    return ClassificationResult(
        classified_type="Unsupported",
        score=0.0,
        per_type_scores=per_type_scores,
        foreign_sections=[],
    )


def _foreign_sections_for(
    classified: SupportedType, doc_sections: dict[str, list]
) -> list[str]:
    """Sections in the doc that aren't part of the classified type's vocabulary."""
    fp = FINGERPRINTS[classified]
    known = set(fp.required_sections) | set(fp.signature_keys.keys())
    return [s for s in doc_sections.keys() if s not in known]
