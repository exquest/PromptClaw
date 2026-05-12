# Buses Recipe

**Labels: supercollider, recipe, buses**

This is a SuperCollider recipe for buses.

```supercollider
// SuperCollider example code for buses
(
SynthDef(\buses, { |out=0, freq=440|
    var sig = SinOsc.ar(freq);
    Out.ar(out, sig);
}).add;
)
```
