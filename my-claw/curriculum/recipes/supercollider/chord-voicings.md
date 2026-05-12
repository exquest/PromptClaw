# Chord Voicings Recipe

**Labels: supercollider, recipe, chord-voicings**

This is a SuperCollider recipe for chord voicings.

```supercollider
// SuperCollider example code for chord-voicings
(
SynthDef(\chordvoicings, { |out=0, freq=440|
    var sig = SinOsc.ar(freq);
    Out.ar(out, sig);
}).add;
)
```
