# Scales Recipe

**Labels: supercollider, recipe, scales**

This is a SuperCollider recipe for scales.

```supercollider
// SuperCollider example code for scales
(
SynthDef(\scales, { |out=0, freq=440|
    var sig = SinOsc.ar(freq);
    Out.ar(out, sig);
}).add;
)
```
