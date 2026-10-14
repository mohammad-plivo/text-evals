# Judging a text walk the way Hunter judges a call

Source: `FHCSD/hunter/v29/build.py` (the suite we ship to Hunter). Hunter sends each call a
`conversationPrompt` (the persona) and an `evaluationPrompt` (the rubric), scores the transcript
against the numbered criteria and passes the call at `evaluationThreshold` 0.8. The text lanes should
grade the same way, so a text result and a Hunter result mean the same thing.

## The three parts Hunter uses

1. **Persona** (`conversationPrompt`). Second person, a real person with a name and a situation, short
   phone sentences, one answer at a time, never an AI, never reveals the test, deflects anything outside
   its facts, and ends with "TARGET is achieved when ...".

2. **Rubric** (`evaluationPrompt`) = a preamble plus numbered criteria. The preamble does four jobs:
   - names the speakers ("the CALLER is the simulated patient, the AGENT is the system under test");
   - says "Judge ONLY the numbered criteria, only the AGENT's behaviour, and do not invent requirements";
   - states the domain facts that make a claim true or invented (the record, the only real slots);
   - states what must NOT be penalised, because a rule the judge is not given is one it invents the
     opposite of (the TeleCRM "Noted" lesson): stating a value once with an acknowledging word is a
     statement, not a question; acknowledging a yes without repeating it is correct; exactly one thing is
     put to the caller for agreement, and a second request is the defect.
   Criteria are one line each, shouted title first, then the test, then the explicit NOT MET condition:
   `ONE BOOKING CONFIRMATION: exactly once, the agent reads the chosen appointment back in full ... It
   does not ask a second time about that same appointment.`
   Write the MET case too when silence would otherwise pass: `If the agent states no appointment detail
   at all, this criterion is MET.`

3. **Threshold**. Hunter passes at 0.8 of the criteria met. A text judge should report the same fraction
   and the same pass line, plus which criteria failed.

## What the text judge adds, and what it cannot have

- Add: the machine facts a transcript cannot show, checked from the run's own report (stored values by
  VALUE under any key, declined fields absent, the exit reached, turn count, request count per turn).
- Cannot have: audio. True barge-in during TTS, wall-clock timing and overlapping speech are not in a
  text walk. Say so in the report rather than let a criterion imply they were tested.

## Shape of a text-lane judgement

Per walk: `criteria_met/criteria_total`, pass if >= 0.8 and every machine fact holds, plus per criterion a
MET/NOT MET with the quoted agent turn that decided it. Per scenario: the pass rate across repeats. Per
arm: the per-criterion failure counts, so a systematic defect is visible rather than averaged away.
