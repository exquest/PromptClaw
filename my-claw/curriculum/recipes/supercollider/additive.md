# Additive Recipe

**Labels: supercollider, recipe, additive**

This is a SuperCollider recipe for additive.

```supercollider
// SuperCollider example code for additive
(
SynthDef(\additive, { |out=0, freq=440|
    var sig = SinOsc.ar(freq);
    Out.ar(out, sig);
}).add;
)
```
