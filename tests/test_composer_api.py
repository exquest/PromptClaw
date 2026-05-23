from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from cypherclaw.composer_api.app import create_app
from cypherclaw.composer_api.schemas import (
    MORPH_CURVE_VALUE_BY_TYPE,
    SUPPORTED_MORPH_CURVE_TYPES,
    SUPPORTED_PHRASE_CURVES,
    SUPPORTED_MORPH_VOICES,
    MorphCurveType,
    MorphPhraseRequest,
    build_morph_phrase_response,
)
from cypherclaw.instrument_morph import MorphInterpolationCurve, morph_curve_position
from cypherclaw.space_reverb import VOICE_REVERB_PROFILES


def test_morph_phrase_schema_normalizes_voice_and_curve_aliases() -> None:
    request = MorphPhraseRequest(
        source_voice=" SW_PLUCK ",
        target_voice="sw_bowed",
        morph_curve_type="equal power",
    )

    assert request.source_voice == "pluck"
    assert request.target_voice == "bowed"
    assert request.morph_curve_type is MorphCurveType.EQUAL_POWER
    response = build_morph_phrase_response(request)

    assert response.model_dump(mode="json") == {
        "accepted": True,
        "source_voice": "pluck",
        "target_voice": "bowed",
        "morph_curve_type": "equal-power",
        "morph_curve_value": 1,
        "synthdef_name": "morph_voice",
    }

    linear = MorphPhraseRequest(
        source_voice="breath",
        target_voice="pad",
        morph_curve_type="linear",
    )
    assert build_morph_phrase_response(linear).morph_curve_value == 0


@pytest.mark.parametrize(
    "payload,expected_text",
    [
        pytest.param(
            {
                "source_voice": "unknown",
                "target_voice": "bowed",
                "morph_curve_type": "linear",
            },
            "source_voice",
            id="unknown-source",
        ),
        pytest.param(
            {
                "source_voice": "pluck",
                "target_voice": "unknown",
                "morph_curve_type": "linear",
            },
            "target_voice",
            id="unknown-target",
        ),
        pytest.param(
            {
                "source_voice": "",
                "target_voice": "bowed",
                "morph_curve_type": "linear",
            },
            "source_voice",
            id="blank-source",
        ),
        pytest.param(
            {
                "source_voice": "pluck",
                "target_voice": "bowed",
                "morph_curve_type": "sigmoid",
            },
            "morph_curve_type",
            id="unsupported-curve",
        ),
        pytest.param(
            {
                "source_voice": "pluck",
                "target_voice": "sw_pluck",
                "morph_curve_type": "equal_power",
            },
            "source_voice and target_voice must differ",
            id="same-normalized-voice",
        ),
    ],
)
def test_morph_phrase_schema_rejects_invalid_payloads(
    payload: dict[str, object],
    expected_text: str,
) -> None:
    with pytest.raises(ValidationError) as exc_info:
        MorphPhraseRequest(**payload)

    assert expected_text in str(exc_info.value)


def test_morph_phrase_endpoint_accepts_valid_request() -> None:
    client = TestClient(create_app())

    response = client.post(
        "/api/v1/composer/morph-phrase",
        json={
            "source_voice": "sw_breath",
            "target_voice": "tabla_tin",
            "morph_curve_type": "equal_power",
        },
    )

    assert response.status_code == 202
    assert response.json() == {
        "accepted": True,
        "source_voice": "breath",
        "target_voice": "tabla_tin",
        "morph_curve_type": "equal-power",
        "morph_curve_value": 1,
        "synthdef_name": "morph_voice",
    }


def test_morph_phrase_endpoint_generates_single_line_phrase_from_voice_pair_and_phrase_curve() -> None:
    client = TestClient(create_app())

    response = client.post(
        "/api/v1/composer/morph-phrase",
        json={
            "source_voice": "sw_pluck",
            "target_voice": "choir",
            "morph_curve_type": "equal_power",
            "phrase_curve": "sigmoid",
            "phrase_frame_count": 5,
        },
    )

    assert response.status_code == 202
    payload = response.json()
    assert payload["accepted"] is True
    assert payload["source_voice"] == "pluck"
    assert payload["target_voice"] == "choir"
    assert payload["morph_curve_type"] == "equal-power"
    assert payload["morph_curve_value"] == 1
    assert payload["synthdef_name"] == "morph_voice"

    phrase = payload["single_line_phrase"]
    assert phrase["source_voice"] == "pluck"
    assert phrase["target_voice"] == "choir"
    assert phrase["phrase_curve"] == "sigmoid"
    assert phrase["frame_count"] == 5
    assert phrase["morph_curve_value"] == 1
    assert phrase["synthdef_name"] == "morph_voice"

    frames = phrase["frames"]
    expected_positions = [0.0, 0.25, 0.5, 0.75, 1.0]
    assert [frame["frame_index"] for frame in frames] == [0, 1, 2, 3, 4]
    assert [frame["position"] for frame in frames] == pytest.approx(
        expected_positions
    )
    assert [frame["morph_x"] for frame in frames] == pytest.approx(
        [morph_curve_position(position, "sigmoid") for position in expected_positions]
    )

    for frame in frames:
        assert frame["synthdef_name"] == "morph_voice"
        assert frame["control_args"] == [
            "morph_x",
            frame["morph_x"],
            "morph_curve",
            1,
        ]


def test_morph_phrase_endpoint_rejects_frame_count_without_phrase_curve() -> None:
    client = TestClient(create_app())

    response = client.post(
        "/api/v1/composer/morph-phrase",
        json={
            "source_voice": "pluck",
            "target_voice": "bowed",
            "morph_curve_type": "linear",
            "phrase_frame_count": 7,
        },
    )

    assert response.status_code == 422
    assert "phrase_frame_count requires phrase_curve" in response.text

    validation_only = client.post(
        "/api/v1/composer/morph-phrase",
        json={
            "source_voice": "pluck",
            "target_voice": "bowed",
            "morph_curve_type": "linear",
        },
    )
    assert validation_only.status_code == 202
    assert "single_line_phrase" not in validation_only.json()


@pytest.mark.parametrize("phrase_curve", [curve.value for curve in MorphInterpolationCurve])
def test_morph_phrase_endpoint_generates_each_phrase_curve_type(
    phrase_curve: str,
) -> None:
    client = TestClient(create_app())

    response = client.post(
        "/api/v1/composer/morph-phrase",
        json={
            "source_voice": "sw_pluck",
            "target_voice": "sw_bowed",
            "morph_curve_type": "equal_power",
            "phrase_curve": phrase_curve,
            "phrase_frame_count": 5,
        },
    )

    assert response.status_code == 202
    phrase = response.json()["single_line_phrase"]
    assert phrase["phrase_curve"] == phrase_curve

    expected_positions = [0.0, 0.25, 0.5, 0.75, 1.0]
    frames = phrase["frames"]
    assert [frame["position"] for frame in frames] == pytest.approx(
        expected_positions
    )
    assert [frame["morph_x"] for frame in frames] == pytest.approx(
        [
            morph_curve_position(position, phrase_curve)
            for position in expected_positions
        ]
    )
    assert frames[0]["morph_x"] == 0.0
    assert frames[-1]["morph_x"] == 1.0


@pytest.mark.parametrize(
    "morph_curve_type,expected_curve_value",
    [
        pytest.param("linear", 0, id="linear"),
        pytest.param("equal-power", 1, id="equal-power"),
    ],
)
def test_morph_phrase_endpoint_generates_each_synth_gain_law_curve_type(
    morph_curve_type: str,
    expected_curve_value: int,
) -> None:
    client = TestClient(create_app())

    response = client.post(
        "/api/v1/composer/morph-phrase",
        json={
            "source_voice": "breath",
            "target_voice": "pad",
            "morph_curve_type": morph_curve_type,
            "phrase_curve": "linear",
            "phrase_frame_count": 3,
        },
    )

    assert response.status_code == 202
    payload = response.json()
    assert payload["morph_curve_value"] == expected_curve_value
    phrase = payload["single_line_phrase"]
    assert phrase["morph_curve_value"] == expected_curve_value
    for frame in phrase["frames"]:
        assert frame["control_args"] == [
            "morph_x",
            frame["morph_x"],
            "morph_curve",
            expected_curve_value,
        ]


@pytest.mark.parametrize(
    "payload,expected_detail",
    [
        pytest.param(
            {
                "source_voice": "pluck",
                "target_voice": "bowed",
                "morph_curve_type": "linear",
                "phrase_curve": "bouncy",
            },
            "phrase_curve",
            id="unsupported-phrase-curve",
        ),
        pytest.param(
            {
                "source_voice": "pluck",
                "target_voice": "bowed",
                "morph_curve_type": "linear",
                "phrase_curve": "linear",
                "phrase_frame_count": 1,
            },
            "phrase_frame_count",
            id="too-few-frames",
        ),
    ],
)
def test_morph_phrase_endpoint_rejects_invalid_phrase_generation_fields(
    payload: dict[str, object],
    expected_detail: str,
) -> None:
    client = TestClient(create_app())

    response = client.post("/api/v1/composer/morph-phrase", json=payload)

    assert response.status_code == 422
    assert expected_detail in response.text


@pytest.mark.parametrize(
    "payload,expected_detail",
    [
        pytest.param(
            {
                "source_voice": "pluck",
                "target_voice": "bowed",
                "morph_curve_type": "linear",
                "tempo": 90,
            },
            "tempo",
            id="extra-field",
        ),
        pytest.param(
            {
                "source_voice": "sw_pad",
                "target_voice": "pad",
                "morph_curve_type": "linear",
            },
            "source_voice and target_voice must differ",
            id="same-normalized-voice",
        ),
        pytest.param(
            {
                "source_voice": "pluck",
                "target_voice": "bowed",
                "morph_curve_type": "sigmoid",
            },
            "morph_curve_type",
            id="unsupported-curve",
        ),
    ],
)
def test_morph_phrase_endpoint_rejects_invalid_requests(
    payload: dict[str, object],
    expected_detail: str,
) -> None:
    client = TestClient(create_app())

    response = client.post("/api/v1/composer/morph-phrase", json=payload)

    assert response.status_code == 422
    assert expected_detail in response.text


def test_morph_phrase_schema_exports_supported_vocabularies() -> None:
    assert SUPPORTED_MORPH_VOICES == tuple(VOICE_REVERB_PROFILES)
    assert "sw_pluck" not in SUPPORTED_MORPH_VOICES
    assert SUPPORTED_MORPH_CURVE_TYPES == ("linear", "equal-power")
    assert SUPPORTED_PHRASE_CURVES == tuple(
        curve.value for curve in MorphInterpolationCurve
    )
    assert MORPH_CURVE_VALUE_BY_TYPE == {
        MorphCurveType.LINEAR: 0,
        MorphCurveType.EQUAL_POWER: 1,
    }

    diagnostic = {
        "voices": SUPPORTED_MORPH_VOICES,
        "curves": SUPPORTED_MORPH_CURVE_TYPES,
        "phrase_curves": SUPPORTED_PHRASE_CURVES,
        "curve_values": {
            curve.value: value
            for curve, value in MORPH_CURVE_VALUE_BY_TYPE.items()
        },
    }
    decoded = json.loads(json.dumps(diagnostic, sort_keys=True))

    assert decoded["voices"] == list(VOICE_REVERB_PROFILES)
    assert decoded["curves"] == ["linear", "equal-power"]
    assert decoded["phrase_curves"] == ["linear", "exponential", "sigmoid"]
    assert decoded["curve_values"] == {"equal-power": 1, "linear": 0}
