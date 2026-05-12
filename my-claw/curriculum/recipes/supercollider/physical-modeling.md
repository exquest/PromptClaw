# Physical Modeling Recipe

**Labels: supercollider, recipe, physical-modeling**

This is a SuperCollider recipe for physical modeling.

```supercollider
// SuperCollider example code for physical-modeling
(
SynthDef(\physicalmodeling, { |out=0, freq=440|
    var sig = SinOsc.ar(freq);
    Out.ar(out, sig);
}).add;
)
```
