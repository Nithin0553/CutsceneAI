# Validation Layers

Target validation compares **target readback** against the **source snapshot / CSIR**, never only against generation requests.

Validation is layered:

1. Structural
2. Numerical timing / transforms
3. Animation / pose / trajectory
4. Camera / framing
5. Audio / event timing
6. Visual
7. Semantic (later)

A transfer may only be committed automatically when all required validation gates for that transfer plan pass.
