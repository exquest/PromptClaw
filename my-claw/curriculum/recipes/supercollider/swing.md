# Swing Recipe

**Labels: supercollider, recipe, swing**

This is a SuperCollider recipe for swing.

```supercollider
// SuperCollider example code for swing
(
SynthDef(\swing, { |out=0, freq=440|
    var sig = SinOsc.ar(freq);
    Out.ar(out, sig);
}).add;
)
```
