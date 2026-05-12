# Granular Recipe

**Labels: supercollider, recipe, granular**

This is a SuperCollider recipe for granular.

```supercollider
// SuperCollider example code for granular
(
SynthDef(\granular, { |out=0, freq=440|
    var sig = SinOsc.ar(freq);
    Out.ar(out, sig);
}).add;
)
```
