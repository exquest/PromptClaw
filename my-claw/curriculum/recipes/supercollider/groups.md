# Groups Recipe

**Labels: supercollider, recipe, groups**

This is a SuperCollider recipe for groups.

```supercollider
// SuperCollider example code for groups
(
SynthDef(\groups, { |out=0, freq=440|
    var sig = SinOsc.ar(freq);
    Out.ar(out, sig);
}).add;
)
```
