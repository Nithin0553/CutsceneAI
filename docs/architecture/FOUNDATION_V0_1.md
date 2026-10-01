# CutsceneAI Foundation v0.1

## Product definition

CutsceneAI transfers an **existing cinematic cutscene** from a source game engine into a target game engine. The source cutscene is the ground truth.

## Studio workflow

```text
CONNECT
  ↓
ANALYZE BOTH PROJECTS
  ↓
SELECT SOURCE CUTSCENE
  ↓
TRANSFER READINESS ANALYSIS
  ↓
TARGET PREPARATION RECOMMENDATIONS
  ↓
RESOLUTION GUIDES
  ↓
RE-ANALYZE
  ↓
REVIEW ASSET / RIG / FEATURE MAPPINGS
  ↓
BUILD TRANSFER PLAN
  ↓
LOSSLESS SOURCE SNAPSHOT
  ↓
CSIR
  ↓
GENERATE IN TARGET STAGING AREA
  ↓
READBACK
  ↓
VALIDATE
  ↓
COMMIT / CORRECT / ROLLBACK
```

## Architectural layers

```text
Studio UI
   ↓
Backend API
   ↓
Project Intelligence
   ↓
Transfer Readiness Advisor
   ↓
Cutscene Element Dictionary (CED)
   ↓
CutsceneAI Interchange Representation (CSIR)
   ↓
Transfer Planner
   ↓
Transfer Runtime
   ├── EXACT
   ├── CONVERTED
   ├── RETARGETED
   ├── BAKED
   ├── RECONSTRUCTED
   ├── TARGET_MAPPED
   └── BLOCKED
   ↓
Engine Adapter
   ↓
Target Staging
   ↓
Readback
   ↓
Validator / Corrector
```

## Separation rules

### CED
Defines what a cinematic element means, independently of any engine.

### CSIR
Stores a specific extracted cutscene using CED vocabulary.

### Engine adapters
Translate between native engine data and CSIR. Core code must not depend on Unity or Unreal APIs.

### Transfer planner
Chooses one explicit handling outcome for every relevant element.

### Validation
Compares source ground truth with target readback, not merely with the generation request.

## Three transfer modes

1. **Structural Transfer** — preserve an editable native equivalent.
2. **Evaluated Transfer** — bake/capture what actually happened when behavior cannot be represented structurally.
3. **Semantic Reconstruction** — recreate the cinematic effect when structural and evaluated transfer cannot preserve it.

## First proof

Use one controlled Unity/Unreal project pair with equivalent assets and one manually authored source cutscene.

```text
Unity Timeline
→ extraction
→ source snapshot
→ CSIR
→ manual mappings
→ Unreal generation
→ Unreal readback
→ numerical validation
```

Automatic matching, complex retargeting, VFX reconstruction and AI must not enter the critical path until this proof works.
