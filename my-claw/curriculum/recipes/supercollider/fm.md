# Fm Recipe

**Labels: supercollider, recipe, fm**

This is a SuperCollider recipe for fm.

```supercollider
// SuperCollider example code for fm
(
SynthDef(\fm, { |out=0, freq=440|
    var sig = SinOsc.ar(freq);
    Out.ar(out, sig);
}).add;
)
```
