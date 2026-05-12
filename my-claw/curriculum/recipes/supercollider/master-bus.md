# Master Bus Recipe

**Labels: supercollider, recipe, master-bus**

This is a SuperCollider recipe for master bus.

```supercollider
// SuperCollider example code for master-bus
(
SynthDef(\masterbus, { |out=0, freq=440|
    var sig = SinOsc.ar(freq);
    Out.ar(out, sig);
}).add;
)
```
