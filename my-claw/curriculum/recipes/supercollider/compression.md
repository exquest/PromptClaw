# Compression Recipe

**Labels: supercollider, recipe, compression**

This is a SuperCollider recipe for compression.

```supercollider
// SuperCollider example code for compression
(
SynthDef(\compression, { |out=0, freq=440|
    var sig = SinOsc.ar(freq);
    Out.ar(out, sig);
}).add;
)
```
