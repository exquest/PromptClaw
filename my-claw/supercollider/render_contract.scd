// render_contract.scd — Reference implementation for reading CypherClaw
// Event metadata from OSC, demonstrating graceful handling of unknown keys.
//
// Usage:  Execute this file in SuperCollider to register the OSC responder.
//         Events arrive as JSON on /cypherclaw/event.

(
// --- Known Pbind keys we act on ----------------------------------------
~knownKeys = Set[\instrument, \midinote, \freq_hz, \dur, \amp, \start, \timingOffset,
	\articulation, \tempoScale, \ampScale, \brightness,
	\ruleStack, \seedPath, \intentTag,
	\phraseStart, \phraseEnd, \cadential,
	\harmonicCharge, \melodicCharge, \metricWeight,
	\phrasePosition, \sectionPosition, \tempoMult, \ampMult,
	\contourApex, \contourApexIndex, \isContourApex,
	\eventId, \phraseId, \sectionId, \voiceId,
	\nominalBeat, \nominalDurBeats, \metadata];

// --- Helper: parse JSON payload into an SC Event -----------------------
~parseEventPayload = { |jsonString|
	var parsed = jsonString.parseJSON;
	var event = ();

	parsed.keysValuesDo { |key, value|
		var sym = key.asSymbol;
		event[sym] = value;
	};

	event;
};

// --- Helper: extract only known keys for Pbind routing -----------------
~extractPbindArgs = { |event|
	var pbind = ();
	event.keysValuesDo { |key, value|
		if (~knownKeys.includes(key)) {
			pbind[key] = value;
		};
		// Unknown keys are silently ignored — forward-compatible with
		// new Event fields added in future render passes.
	};
	pbind;
};

// --- OSC responder for /cypherclaw/event -------------------------------
~cypherclawResponder.free;  // idempotent cleanup
~cypherclawResponder = OSCFunc({ |msg, time, addr, recvPort|
	var jsonPayload = msg[1].asString;
	var event = ~parseEventPayload.(jsonPayload);
	var pbind = ~extractPbindArgs.(event);

	// Route to the appropriate SynthDef based on instrument key
	var synthName = pbind[\instrument] ? \default;

	// Provenance metadata — available for logging/debugging but not
	// sent to the synth engine.
	var ruleStack = pbind[\ruleStack];
	var seedPath  = pbind[\seedPath];

	// Play the note via the server. When the composer supplies freq_hz
	// directly (e.g. non-12-TET tunings), use it as-is. Otherwise fall
	// back to midicps over midinote for backward-compatible 12-TET scenes.
	Synth(synthName, [
		\freq,       pbind[\freq_hz] ?? { (pbind[\midinote] ? 60).midicps },
		\dur,        pbind[\dur] ? 0.5,
		\amp,        pbind[\amp] ? 0.5,
		\brightness, pbind[\brightness] ? 0.0,
		\tempoScale, pbind[\tempoScale] ? 1.0,
		\ampScale,   pbind[\ampScale] ? 1.0,
	]);

	// Optional: log provenance for debugging
	if (ruleStack.notNil) {
		Post << "  rules: " << ruleStack << Char.nl;
	};
	if (seedPath.notNil) {
		Post << "  seed:  " << seedPath << Char.nl;
	};

}, '/cypherclaw/event');

"CypherClaw render contract OSC responder registered on /cypherclaw/event".postln;
)
