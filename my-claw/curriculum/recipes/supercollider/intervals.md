# Intervals Recipe

**Labels: supercollider, recipe, intervals**

This is a SuperCollider recipe for intervals.

```supercollider
// SuperCollider example code for intervals
(
SynthDef(\intervals, { |out=0, freq=440|
    var sig = SinOsc.ar(freq);
    Out.ar(out, sig);
}).add;
)
```
