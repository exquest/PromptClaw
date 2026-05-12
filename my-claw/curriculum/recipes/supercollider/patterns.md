# Patterns Recipe

**Labels: supercollider, recipe, patterns**

This is a SuperCollider recipe for patterns.

```supercollider
// SuperCollider example code for patterns
(
SynthDef(\patterns, { |out=0, freq=440|
    var sig = SinOsc.ar(freq);
    Out.ar(out, sig);
}).add;
)
```
