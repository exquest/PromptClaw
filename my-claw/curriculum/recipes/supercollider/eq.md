# Eq Recipe

**Labels: supercollider, recipe, eq**

This is a SuperCollider recipe for eq.

```supercollider
// SuperCollider example code for eq
(
SynthDef(\eq, { |out=0, freq=440|
    var sig = SinOsc.ar(freq);
    Out.ar(out, sig);
}).add;
)
```
