"""Reproducible, conservative CED-to-native mapping pretraining.

This fits a TF-IDF semantic retriever over the CED vocabulary and the checked-in
Unity/Unreal draft native-name dictionaries, with registered-rule associations.
It genuinely learns token statistics from the 735-concept corpus, but cannot
learn native conversion *success* without independent real-engine feedback.

Output is advisory only; a match never authorizes a new resolver or native
mutation. The deterministic adaptive mapper and native preflight remain
authoritative. Training is fully offline and uses only Python's stdlib.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Mapping

MODEL_KIND = "cutsceneai.ced.semantic_mapping_pretraining"
MODEL_VERSION = "1"
SOURCES = {
    "ced": "cutscene-elements-v0.2.json",
    "rules": "adaptive-rules-v0.1.json",
    "unity": "unity-mappings-v0.1.json",
    "unreal": "unreal-mappings-v0.1.json",
    "preflight": "unity-unreal-preflight-v0.2.json",
}
CONTRACT_DIR = Path(__file__).resolve().parents[1] / "contracts" / "dictionary"


class CEDPretrainingError(ValueError):
    """Reject invalid CED supervision, stale checkpoints and unsafe retrieval."""


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, ensure_ascii=False,
        separators=(",", ":"), allow_nan=False,
    ).encode("utf-8")


def _sha(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _tokens(value: str) -> list[str]:
    """Split Python/Unity/Unreal native names into comparable semantic tokens."""
    if not isinstance(value, str) or len(value) > 256:
        raise CEDPretrainingError("Native/CED semantic token must be bounded text.")
    expanded = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", value)
    return re.findall(r"[a-z]+|[0-9]+", expanded.casefold())


def _catalogs(inputs: Mapping[str, dict]) -> tuple[list[str], dict, dict, dict]:
    taxonomy = inputs["ced"].get("categories")
    if not isinstance(taxonomy, dict) or not taxonomy:
        raise CEDPretrainingError("Invalid CED taxonomy.")
    concepts = []
    for name, rows in sorted(taxonomy.items()):
        if not isinstance(name, str) or not isinstance(rows, list):
            raise CEDPretrainingError("Malformed CED semantic category.")
        for ced in rows:
            if not isinstance(ced, str) or not ced.startswith(name + "."):
                raise CEDPretrainingError("CED concepts must be fully qualified and categorized.")
            concepts.append(ced)
    if len(concepts) != len(set(concepts)):
        raise CEDPretrainingError("Duplicate CED semantic ID.")
    concepts = sorted(concepts)
    vocab = set(concepts)
    aliases = {"unity": defaultdict(set), "unreal": defaultdict(set)}
    by_concept = defaultdict(set)
    for engine in ("unity", "unreal"):
        data = inputs[engine]
        if data.get("engine") != engine or not isinstance(data.get("mappings"), list):
            raise CEDPretrainingError("Native mapping table has wrong engine.")
        for row in data["mappings"]:
            if (not isinstance(row, dict) or row.get("ced") not in vocab
                    or not isinstance(row.get("native"), list)
                    or not row["native"]):
                raise CEDPretrainingError("Unknown CED ID or empty native alias in mapping table.")
            for native in row["native"]:
                if not isinstance(native, str) or not _tokens(native):
                    raise CEDPretrainingError("Invalid native mapping alias.")
                aliases[engine][native.casefold()].add(row["ced"])
                by_concept[row["ced"]].update(_tokens(native))
    rules = inputs["rules"].get("rules")
    if not isinstance(rules, list):
        raise CEDPretrainingError("Missing approved-rule vocabulary.")
    registered = defaultdict(set)
    for rule in rules:
        if (not isinstance(rule, dict) or rule.get("ced") not in vocab
                or not isinstance(rule.get("rule_id"), str)
                or not isinstance(rule.get("resolution"), dict)
                or not isinstance(rule["resolution"].get("resolver"), str)):
            raise CEDPretrainingError("Adaptive mapping rule references unknown CED semantics.")
        registered[rule["ced"]].add(rule["rule_id"])
    return concepts, {
        engine: {native: sorted(ids) for native, ids in sorted(rows.items())}
        for engine, rows in aliases.items()
    }, {name: sorted(values) for name, values in by_concept.items()}, {
        name: sorted(values) for name, values in registered.items()
    }


def _fit(concepts: list[str], extra: Mapping[str, list[str]] | None = None) -> tuple[dict, dict]:
    """Fit normalized TF-IDF vectors from real CED IDs and optional native aliases."""
    documents: dict[str, Counter[str]] = {}
    document_frequency: Counter[str] = Counter()
    for ced in concepts:
        terms = _tokens(ced) + list((extra or {}).get(ced, []))
        counts = Counter(terms)
        documents[ced] = counts
        document_frequency.update(counts.keys())
    size = len(concepts)
    idf = {token: round(math.log((size + 1) / (count + 1)) + 1, 9)
           for token, count in sorted(document_frequency.items())}
    vectors = {}
    for ced, counts in sorted(documents.items()):
        raw = {token: value * idf[token] for token, value in counts.items()}
        length = math.sqrt(sum(v * v for v in raw.values()))
        vectors[ced] = {
            token: round(value / length, 9)
            for token, value in sorted(raw.items())
        } if length else {}
    return idf, vectors


def _rank(idf: Mapping[str, float], vectors: Mapping[str, dict],
          native: str, *, limit: int = 5) -> list[tuple[str, float]]:
    query = Counter(_tokens(native))
    # A shared generic word such as "native" or "actor" is not enough to
    # assert a new semantic mapping for an otherwise unseen component name.
    in_vocabulary = sum(count for term, count in query.items() if term in idf)
    if in_vocabulary * 2 < sum(query.values()):
        return []
    raw = {term: count * idf[term]
           for term, count in query.items() if term in idf}
    norm = math.sqrt(sum(v * v for v in raw.values()))
    if norm < 1e-12:
        return []
    q = {term: value / norm for term, value in raw.items()}
    scores = [
        (ced, round(sum(weight * q.get(term, 0.0)
                        for term, weight in vec.items()), 8))
        for ced, vec in vectors.items()
    ]
    return sorted((row for row in scores if row[1] > 0),
                  key=lambda row: (-row[1], row[0]))[:limit]



def _preflight_supervision(document: dict, concepts: list[str]) -> tuple[dict, dict]:
    """Fit capability/refusal labels without treating them as native test rewards."""
    if (document.get("source_engine") != "unity"
            or document.get("target_engine") != "unreal"):
        raise CEDPretrainingError("Wrong source/target engine in preflight labels.")
    known = set(concepts)
    valid = {"SUPPORTED_UNVERIFIED", "KNOWN_PARTIAL", "KNOWN_UNSUPPORTED"}
    policy = {}
    for domain in ("tracks", "sections", "curve_semantics"):
        values = document.get(domain)
        if not isinstance(values, dict):
            raise CEDPretrainingError("Missing preflight domain " + domain)
        policy[domain] = {}
        for ced, value in sorted(values.items()):
            state = (value.get("state") if isinstance(value, dict) else value)
            if ced not in known or state not in valid:
                raise CEDPretrainingError("Invalid CED capability state.")
            policy[domain][ced] = state
    generics = defaultdict(set)
    for domain in ("generic_native_tracks", "generic_native_sections"):
        for native, value in document.get(domain, {}).items():
            if (not isinstance(value, dict) or value.get("ced") not in known
                    or value.get("state") not in valid or not _tokens(native)):
                raise CEDPretrainingError("Invalid generic native mapping evidence.")
            generics[native.casefold()].add(value["ced"])
    return policy, {k: sorted(v) for k, v in sorted(generics.items())}


def fit(inputs: Mapping[str, dict], *, input_hashes: Mapping[str, str]) -> dict:
    """Train CED semantic/native association policy with real source labels.

    Native aliases are draft reference data, not validated runtime conversions.
    Zero-shot holdout measures unseen alias lexical retrieval *before* native
    mappings are included in the fitted model; it is not a fidelity metric.
    """
    if set(inputs) != set(SOURCES) or set(input_hashes) != set(SOURCES):
        raise CEDPretrainingError("Every pinned CED training source is required.")
    concepts, aliases, native_tokens, registered = _catalogs(inputs)

    # Evaluate truly unseen engine-native aliases against CED-only vocabulary.
    # No alias used in this evaluation enters the CED-only fit.
    base_idf, base_vectors = _fit(concepts)
    trials = 0
    top1 = 0
    top3 = 0
    for engine in ("unity", "unreal"):
        for native, expected in sorted(aliases[engine].items()):
            ranked = [ced for ced, _ in _rank(base_idf, base_vectors, native, limit=3)]
            trials += 1
            top1 += bool(ranked and ranked[0] in expected)
            top3 += bool(set(ranked) & set(expected))

    capability_states, generic_aliases = _preflight_supervision(
        inputs["preflight"], concepts)
    for native, ids in generic_aliases.items():
        aliases["unity"][native] = sorted(
            set(aliases["unity"].get(native, [])) | set(ids))
        for ced in ids:
            native_tokens[ced] = sorted(
                set(native_tokens.get(ced, [])) | set(_tokens(native)))
    idf, vectors = _fit(concepts, native_tokens)
    unity_concepts = {ced for items in aliases["unity"].values() for ced in items}
    unreal_concepts = {ced for items in aliases["unreal"].values() for ced in items}
    model = {
        "kind": MODEL_KIND,
        "schema_version": MODEL_VERSION,
        "training_type": "SUPERVISED_CED_SEMANTIC_NATIVE_RETRIEVAL",
        "training_input_sha256": dict(sorted(input_hashes.items())),
        "ced_version": inputs["ced"].get("version"),
        "stats": {
            "ced_concepts": len(concepts),
            "ced_categories": len(inputs["ced"]["categories"]),
            "registered_rule_examples": sum(map(len, registered.values())),
            "unity_native_aliases": len(aliases["unity"]),
            "unreal_native_aliases": len(aliases["unreal"]),
            "ced_concepts_with_both_native_draft_mappings":
                len(unity_concepts & unreal_concepts),
            "independent_native_reward_examples": 0,
            "preflight_domain_labels": sum(len(v) for v in capability_states.values()),
            "preflight_partial_or_unsupported_labels": sum(
                state != "SUPPORTED_UNVERIFIED"
                for labels in capability_states.values() for state in labels.values()),
            "generic_native_aliases": len(generic_aliases),
        },
        "evaluation": {
            "method": "CED_ONLY_ZERO_SHOT_NATIVE_ALIAS_RETRIEVAL",
            "alias_holdout_count": trials,
            "top1_hits": top1,
            "top3_hits": top3,
            "accuracy_is_not_native_conversion_success": True,
        },
        "idf": idf,
        "concept_vectors": vectors,
        "native_alias_index": aliases,
        "preflight_capability_states": capability_states,
        "registered_rule_ids": dict(sorted(registered.items())),
        "unmapped_concepts_need_new_adapter": True,
        "native_conversion_authorized": False,
        "trained_on_real_unreal_rewards": False,
    }
    model["payload_sha256"] = _sha(model)
    return model


def read_sources(folder: str | Path = CONTRACT_DIR) -> tuple[dict, dict]:
    root = Path(folder)
    values = {}
    hashes = {}
    for name, filename in SOURCES.items():
        path = root / filename
        if (path.is_symlink() or any(part.is_symlink() for part in path.parents)
                or not path.is_file() or not 0 < path.stat().st_size <= 2 * 1024 * 1024):
            raise CEDPretrainingError("CED training source is missing or unsafe: " + filename)
        data = path.read_bytes()
        hashes[name] = hashlib.sha256(data).hexdigest()
        try:
            values[name] = json.loads(data.decode("utf-8-sig"))
        except (UnicodeError, ValueError) as exc:
            raise CEDPretrainingError("Invalid CED source JSON: " + filename) from exc
        if not isinstance(values[name], dict):
            raise CEDPretrainingError("CED source must be a JSON object: " + filename)
    return values, hashes


def train(folder: str | Path = CONTRACT_DIR) -> dict:
    inputs, hashes = read_sources(folder)
    return fit(inputs, input_hashes=hashes)


def validate(model: Any, *, folder: str | Path = CONTRACT_DIR,
             require_current_inputs: bool = True) -> dict:
    if not isinstance(model, dict) or model.get("kind") != MODEL_KIND:
        raise CEDPretrainingError("Unrecognized trained CED model.")
    digest = model.get("payload_sha256")
    data = {key: value for key, value in model.items() if key != "payload_sha256"}
    if not isinstance(digest, str) or digest != _sha(data):
        raise CEDPretrainingError("Trained CED model was modified after fitting.")
    if model.get("native_conversion_authorized") is not False:
        raise CEDPretrainingError("Semantic training cannot authorize engine writes.")
    if require_current_inputs:
        inputs, hashes = read_sources(folder)
        if hashes != model.get("training_input_sha256"):
            raise CEDPretrainingError("Trained CED model is stale for current rulebook.")
        # A plain SHA256 is not a signature; anyone can rehash a forged
        # checkpoint. Require the model to reproduce from the pinned,
        # checked-in CED and mapping contracts before offering suggestions.
        if fit(inputs, input_hashes=hashes) != model:
            raise CEDPretrainingError(
                "Trained CED model does not reproduce from trusted rule sources.")
    return model


def suggest(model: dict, native_name: str, *, engine: str, limit: int = 5) -> list[dict]:
    """Propose mappings; native execution always requires independent approval."""
    validate(model)
    if engine not in ("unity", "unreal") or type(limit) is not int or not 1 <= limit <= 10:
        raise CEDPretrainingError("Unsupported mapping search scope.")
    if not isinstance(native_name, str) or not native_name.strip():
        raise CEDPretrainingError("Mapping query cannot be empty.")
    alias_hits = model["native_alias_index"][engine].get(native_name.casefold(), [])
    ranked = _rank(model["idf"], model["concept_vectors"], native_name, limit=limit)
    result: list[dict] = []
    for ced in alias_hits:
        result.append({
            "ced": ced, "match": "DRAFT_NATIVE_ALIAS",
            "score": 1.0, "registered_rule_ids":
                model["registered_rule_ids"].get(ced, []),
            "preflight_states": {
                domain: labels[ced] for domain, labels
                in model["preflight_capability_states"].items() if ced in labels
            },
            "native_conversion_authorized": False,
        })
    for ced, score in ranked:
        if any(row["ced"] == ced for row in result):
            continue
        result.append({
            "ced": ced, "match": "TRAINED_LEXICAL_SIMILARITY",
            "score": score, "registered_rule_ids":
                model["registered_rule_ids"].get(ced, []),
            "preflight_states": {
                domain: labels[ced] for domain, labels
                in model["preflight_capability_states"].items() if ced in labels
            },
            "native_conversion_authorized": False,
        })
    return result[:limit]
