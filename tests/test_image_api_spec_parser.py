"""Tests for image_api.spec_parser — Shape A + Shape B YAML parsing."""
from __future__ import annotations

import json

import pytest

from cypherclaw.image_api.schemas import InternalSpec
from cypherclaw.image_api.spec_parser import SpecParseError, parse_spec_yaml


# ---------------------------------------------------------------------------
# Shape A: explicit prompt
# ---------------------------------------------------------------------------

class TestShapeA:
    def test_explicit_prompt_round_trips(self):
        yaml_text = """
project: hat
prompt: "A dramatic hero image showing a crashing financial dashboard"
style: modern
dimensions: 1024x768
filename: hero.jpg
content_piece_id: 42
"""
        spec = parse_spec_yaml(yaml_text, project_slug="hat")
        assert isinstance(spec, InternalSpec)
        assert spec.project == "hat"
        assert spec.prompt.startswith("A dramatic hero image")
        assert spec.style == "modern"
        assert (spec.width, spec.height) == (1024, 768)
        assert spec.filename == "hero.jpg"
        assert spec.content_piece_id == 42

    def test_minimal_prompt_only(self):
        spec = parse_spec_yaml("prompt: simple", project_slug="proj")
        assert spec.prompt == "simple"
        # defaults
        assert (spec.width, spec.height) == (1024, 1024)
        assert spec.filename == "image.png"
        assert spec.content_piece_id is None
        assert spec.style is None

    def test_prompt_with_extra_whitespace_is_stripped(self):
        spec = parse_spec_yaml("prompt: '   padded   '", project_slug="p")
        assert spec.prompt == "padded"

    def test_x_separator_variants_in_dimensions(self):
        for dim in ("512x512", "512X512", "512×512", " 800 x 600 "):
            spec = parse_spec_yaml(f"prompt: x\ndimensions: '{dim}'", project_slug="p")
            assert spec.width > 0 and spec.height > 0

    def test_invalid_dimensions_rejected(self):
        with pytest.raises(SpecParseError, match="dimensions"):
            parse_spec_yaml("prompt: x\ndimensions: 'huge'", project_slug="p")


# ---------------------------------------------------------------------------
# Shape B: content-derived
# ---------------------------------------------------------------------------

class TestShapeB:
    YAML_B = """
project: cascadian-tickets
content_type: blog
title: "5 ways to handle last-minute event changes"
description: "Short outline of the post body used to derive image intent"
media_type: hero_image
platform: blog
"""

    def test_derives_prompt_from_title_description(self):
        spec = parse_spec_yaml(self.YAML_B, project_slug="cascadian-tickets")
        assert "5 ways to handle last-minute event changes" in spec.prompt
        assert "Short outline" in spec.prompt
        assert spec.project == "cascadian-tickets"

    def test_media_type_appears_in_prompt(self):
        spec = parse_spec_yaml(self.YAML_B, project_slug="cascadian-tickets")
        assert "hero image" in spec.prompt.lower()

    def test_platform_appears_in_prompt(self):
        spec = parse_spec_yaml(self.YAML_B, project_slug="cascadian-tickets")
        assert "blog" in spec.prompt.lower()

    def test_title_only_without_description(self):
        yaml_text = "title: 'Just a title'\nmedia_type: thumbnail"
        spec = parse_spec_yaml(yaml_text, project_slug="x")
        assert "Just a title" in spec.prompt

    def test_empty_shape_b_rejected(self):
        # Neither prompt nor title nor description
        with pytest.raises(SpecParseError, match="prompt"):
            parse_spec_yaml("media_type: hero_image", project_slug="x")


# ---------------------------------------------------------------------------
# Project slug coherence
# ---------------------------------------------------------------------------

class TestProjectSlugCoherence:
    def test_request_slug_wins(self):
        spec = parse_spec_yaml("project: foo\nprompt: x", project_slug="foo")
        assert spec.project == "foo"

    def test_mismatched_project_rejected(self):
        with pytest.raises(SpecParseError, match="disagrees"):
            parse_spec_yaml("project: foo\nprompt: x", project_slug="bar")

    def test_missing_project_in_spec_uses_request_slug(self):
        spec = parse_spec_yaml("prompt: x", project_slug="bar")
        assert spec.project == "bar"


# ---------------------------------------------------------------------------
# Failure paths
# ---------------------------------------------------------------------------

class TestErrors:
    def test_empty_yaml_rejected(self):
        with pytest.raises(SpecParseError, match="empty"):
            parse_spec_yaml("", project_slug="p")

    def test_non_mapping_root_rejected(self):
        with pytest.raises(SpecParseError, match="mapping"):
            parse_spec_yaml("- a\n- b", project_slug="p")

    def test_invalid_yaml_rejected(self):
        with pytest.raises(SpecParseError, match="invalid YAML"):
            parse_spec_yaml("key: [unterminated", project_slug="p")

    def test_invalid_content_piece_id_rejected(self):
        with pytest.raises(SpecParseError, match="content_piece_id"):
            parse_spec_yaml("prompt: x\ncontent_piece_id: not_an_int", project_slug="p")


# ---------------------------------------------------------------------------
# Model override pass-through
# ---------------------------------------------------------------------------

class TestModelOverride:
    def test_model_field_propagates_to_spec(self):
        spec = parse_spec_yaml(
            "prompt: x\nmodel: gemini-3.1-flash-image-preview",
            project_slug="p",
        )
        assert spec.model_override == "gemini-3.1-flash-image-preview"

    def test_no_model_means_none(self):
        spec = parse_spec_yaml("prompt: x", project_slug="p")
        assert spec.model_override is None


class TestImageApiSpecParserEndToEnd:
    def test_shape_a_and_shape_b_normalize_to_json_safe_internal_specs(self) -> None:
        cases = [
            {
                "name": "explicit-prompt",
                "project_slug": "hat",
                "yaml": """
project: hat
prompt: "A dramatic product hero with a bold financial dashboard"
style: editorial
dimensions: 640X480
filename: hero.jpg
content_piece_id: "77"
model: gemini-3.1-flash-image-preview
""",
                "prompt_fragments": [
                    "dramatic product hero",
                    "financial dashboard",
                ],
                "width": 640,
                "height": 480,
                "filename": "hero.jpg",
                "style": "editorial",
                "content_piece_id": 77,
                "model_override": "gemini-3.1-flash-image-preview",
            },
            {
                "name": "content-derived",
                "project_slug": "cascadian-tickets",
                "yaml": """
project: cascadian-tickets
content_type: blog
title: "5 ways to handle last-minute event changes"
description: "Short outline of the post body used to derive image intent"
media_type: hero_image
platform: blog
style: documentary
dimensions: [1200, 630]
""",
                "prompt_fragments": [
                    "hero image",
                    "5 ways to handle last-minute event changes",
                    "Short outline of the post body",
                    "Composed for blog",
                    "Treat as a blog accompaniment",
                    "Style: documentary",
                ],
                "width": 1200,
                "height": 630,
                "filename": "image.png",
                "style": "documentary",
                "content_piece_id": None,
                "model_override": None,
            },
        ]

        for case in cases:
            spec = parse_spec_yaml(
                str(case["yaml"]),
                project_slug=str(case["project_slug"]),
            )
            payload = spec.model_dump(mode="json")
            json.dumps(payload, sort_keys=True)

            assert isinstance(spec, InternalSpec)
            assert payload["project"] == case["project_slug"], case["name"]
            assert payload["width"] == case["width"], case["name"]
            assert payload["height"] == case["height"], case["name"]
            assert payload["filename"] == case["filename"], case["name"]
            assert payload["style"] == case["style"], case["name"]
            assert payload["content_piece_id"] == case["content_piece_id"], case["name"]
            assert payload["model_override"] == case["model_override"], case["name"]
            for fragment in case["prompt_fragments"]:
                assert str(fragment) in spec.prompt, case["name"]
