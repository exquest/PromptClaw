# Envelopes Recipe

**Labels: supercollider, recipe, envelopes**

This is a SuperCollider recipe for envelopes.

```supercollider
// SuperCollider example code for envelopes
(
SynthDef(\envelopes, { |out=0, freq=440|
    var sig = SinOsc.ar(freq);
    Out.ar(out, sig);
}).add;
)
```
