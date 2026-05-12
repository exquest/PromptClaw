# Reverb Recipe

**Labels: supercollider, recipe, reverb**

This is a SuperCollider recipe for reverb.

```supercollider
// SuperCollider example code for reverb
(
SynthDef(\reverb, { |out=0, freq=440|
    var sig = SinOsc.ar(freq);
    Out.ar(out, sig);
}).add;
)
```
