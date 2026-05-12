# Midi To Frequency Recipe

**Labels: supercollider, recipe, midi-to-frequency**

This is a SuperCollider recipe for midi to frequency.

```supercollider
// SuperCollider example code for midi-to-frequency
(
SynthDef(\miditofrequency, { |out=0, freq=440|
    var sig = SinOsc.ar(freq);
    Out.ar(out, sig);
}).add;
)
```
