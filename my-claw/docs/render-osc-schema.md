# Render OSC Bundle Schema

## Transport

Each rendered Event is sent as a single OSC bundle containing one message.

```
#bundle\0          (8 bytes)
<timetag>          (8 bytes, immediate = 0x0000000000000001)
<element-size>     (4 bytes, big-endian int32)
<osc-message>      (variable)
```

### OSC Message

| Field      | Value                     |
|------------|---------------------------|
| Address    | `/cypherclaw/event`       |
| Type tags  | `,s`                      |
| Argument   | JSON-encoded Event object |

The JSON payload is the canonical representation produced by `Event.to_json()`.

## Pbind Dictionary Format

For direct SuperCollider Pbind integration, `event_to_pbind_dict()` in
`music_tracker_runtime.py` produces a flat key-value mapping with
SC-idiomatic camelCase keys.  All values are primitives (number or string)
so they survive OSC string/float transport unchanged.

### Field Mapping

| Event field                    | Pbind key          | Type    | Notes                              |
|--------------------------------|--------------------|---------|------------------------------------|
| `event_id`                     | `eventId`          | string  |                                    |
| `phrase_id`                    | `phraseId`         | string  |                                    |
| `section_id`                   | `sectionId`        | string  |                                    |
| `voice_id`                     | `voiceId`          | string  |                                    |
| `role`                         | `instrument`       | string  | Maps to SynthDef routing           |
| `pitch`                        | `midinote`         | number  | MIDI note; `""` when rest          |
| `nominal_beat`                 | `nominalBeat`      | float   |                                    |
| `nominal_dur_beats`            | `nominalDurBeats`  | float   |                                    |
| `harmonic_charge`              | `harmonicCharge`   | float   |                                    |
| `melodic_charge`               | `melodicCharge`    | float   |                                    |
| `metric_weight`                | `metricWeight`     | float   |                                    |
| `is_phrase_start`              | `phraseStart`      | int     | `1` / `0`                          |
| `is_phrase_end`                | `phraseEnd`        | int     | `1` / `0`                          |
| `is_cadential`                 | `cadential`        | int     | `1` / `0`                          |
| `intent_tag`                   | `intentTag`        | string  | One of IntentTag values or `""`    |
| `onset_sec`                    | `start`            | float   | Absolute onset in seconds          |
| `dur_sec`                      | `dur`              | float   | Duration in seconds                |
| `velocity`                     | `amp`              | float   | Amplitude `[0, 1]`                 |
| `timing_deviation_ms`          | `timingOffset`     | float   | Microtiming offset in ms           |
| `articulation`                 | `articulation`     | string  | e.g. `"legato"`, `"staccato"`      |
| `sensor_tempo_scale`           | `tempoScale`       | float   | Live tempo modulation              |
| `sensor_amp_scale`             | `ampScale`         | float   | Live amplitude modulation          |
| `sensor_brightness`            | `brightness`       | float   | Live spectral modulation           |
| `rule_stack`                   | `ruleStack`        | string  | JSON array of applied rule names   |
| `seed_path`                    | `seedPath`         | string  | JSON array of ints for RNG replay  |
| `normalized_phrase_position`   | `phrasePosition`   | float   | `[0, 1]`                           |
| `normalized_section_position`  | `sectionPosition`  | float   | `[0, 1]`                           |
| `tempo_mult`                   | `tempoMult`        | float   |                                    |
| `amp_mult`                     | `ampMult`          | float   |                                    |
| `contour_apex`                 | `contourApex`      | float   |                                    |
| `contour_apex_index`           | `contourApexIndex` | int     | `""` when absent                   |
| `is_contour_apex`              | `isContourApex`    | int     | `1` / `0`                          |
| `metadata`                     | `metadata`         | string  | JSON object of additional metadata |

### Complex-field encoding

| Python type       | Pbind value    | Decode                    |
|-------------------|----------------|---------------------------|
| `bool`            | `1` / `0`      | truthy check              |
| `list[str]`       | JSON string    | `json.loads` / `parseJSON`|
| `tuple[int, ...]` | JSON int array | `json.loads` / `parseJSON`|
| `dict`            | JSON string    | `json.loads` / `parseJSON`|
| `None`            | `""`           | check for empty string    |

### Round-trip guarantee

```python
from cypherclaw.render.events import Event
from senseweave.music_tracker_runtime import event_to_pbind_dict, pbind_dict_to_event

event = Event(rule_stack=["R2", "R8"], seed_path=(7, 11), pitch=64)
restored = pbind_dict_to_event(event_to_pbind_dict(event))
assert restored == event
```

### Excluded fields

`section_envelope` and `phrase` are not included in the Pbind mapping because
they are complex nested structures not suitable for flat OSC transport.
They remain available through the full JSON bundle via `Event.to_osc_bundle()`.
