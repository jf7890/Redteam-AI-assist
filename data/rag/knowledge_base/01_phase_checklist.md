# Redteam Lab Phase Checklist

## Recon
- Build a target inventory for every in-scope host.
- Record service versions and any unusual exposed ports.
- Save at least one evidence note per host.

## Enumeration
- For each discovered service, collect deeper context.
- Capture endpoint behavior or protocol details.
- Flag anomalies that can justify a hypothesis.

## Hypothesis
- Write 1-3 ranked hypotheses.
- For each hypothesis, define one safe validation method.
- Keep assumptions explicit in notes.

## Attempt
- Validate the top-ranked hypothesis using only allowed tools.
- Capture pass/fail result with timestamp and command evidence.
- Avoid repeated attempts without updating assumptions.

## Post-check
- Verify impact boundaries within the lab scope only.
- Capture cleanup or reset notes required by instructors.

## Report
- Build a timeline from recon to final validation.
- Link each finding to evidence references.
- Include failed paths and why they were rejected.
