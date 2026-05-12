# Subtractive Recipe

**Labels: supercollider, recipe, subtractive**

This is a SuperCollider recipe for subtractive.

```supercollider
// SuperCollider example code for subtractive
(
SynthDef(\subtractive, { |out=0, freq=440|
    var sig = SinOsc.ar(freq);
    Out.ar(out, sig);
}).add;
)
```
