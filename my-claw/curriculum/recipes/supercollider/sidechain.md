# Sidechain Recipe

**Labels: supercollider, recipe, sidechain**

This is a SuperCollider recipe for sidechain.

```supercollider
// SuperCollider example code for sidechain
(
SynthDef(\sidechain, { |out=0, freq=440|
    var sig = SinOsc.ar(freq);
    Out.ar(out, sig);
}).add;
)
```
