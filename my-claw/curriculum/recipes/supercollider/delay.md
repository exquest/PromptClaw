# Delay Recipe

**Labels: supercollider, recipe, delay**

This is a SuperCollider recipe for delay.

```supercollider
// SuperCollider example code for delay
(
SynthDef(\delay, { |out=0, freq=440|
    var sig = SinOsc.ar(freq);
    Out.ar(out, sig);
}).add;
)
```
