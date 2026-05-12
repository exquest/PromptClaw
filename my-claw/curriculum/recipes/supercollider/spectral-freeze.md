# Spectral Freeze Recipe

**Labels: supercollider, recipe, spectral-freeze**

This is a SuperCollider recipe for spectral freeze.

```supercollider
// SuperCollider example code for spectral-freeze
(
SynthDef(\spectralfreeze, { |out=0, freq=440|
    var sig = SinOsc.ar(freq);
    Out.ar(out, sig);
}).add;
)
```
