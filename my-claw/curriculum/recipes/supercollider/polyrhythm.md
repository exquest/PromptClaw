# Polyrhythm Recipe

**Labels: supercollider, recipe, polyrhythm**

This is a SuperCollider recipe for polyrhythm.

```supercollider
// SuperCollider example code for polyrhythm
(
SynthDef(\polyrhythm, { |out=0, freq=440|
    var sig = SinOsc.ar(freq);
    Out.ar(out, sig);
}).add;
)
```
