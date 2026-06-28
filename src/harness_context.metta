; Patch 4 Candidate: MeTTa-owned continuity context policy.
;
; Python may read these atoms mechanically to render prompt-facing context
; views. Raw history remains exact; these declarations only govern what is
; shown in the prompt context.

(ContextRole human-message)
(ContextRole pin)
(ContextRole send)
(ContextRole skill-result)
(ContextRole raw-result)
(ContextRole recall-result)
(ContextRole artifact-pointer)
(ContextRole error)
(ContextRole prompt-echo)
(ContextRole anti-spam-echo)
(ContextRole wake-chatter)
(ContextRole duplicate-error)
(ContextRole repeated-skill-result)

(ContextWindow human-message full 1)
(ContextWindow human-message compact 6)
(ContextWindow human-message breadcrumb 12)

(ContextWindow pin full 1)
(ContextWindow pin compact 7)
(ContextSingleton pin)

(ContextWindow send exact 6)
(ContextNoCompact send)

(ContextWindow artifact-pointer compact 16)
(ContextWindow recall-result compact 10)
(ContextWindow error compact 3)

(ContextFresh raw-result full 2)
(ContextFresh raw-result excerpt 3)
(ContextFresh raw-result pointer 8)

(ContextFresh recall-result full 1)
(ContextFresh recall-result excerpt 5)
(ContextFresh recall-result pointer 12)

(ContextFresh error full 1)
(ContextFresh error compact 3)

(ContextLarge raw-result 6000)
(ContextLarge send 6000)

(ContextOmitAlways prompt-echo)
(ContextOmitAlways anti-spam-echo)
(ContextOmitAlways wake-chatter)

(ContextCollapse repeated-skill-result)
(ContextCollapse duplicate-error)
(ContextPointer artifact-pointer)

(= (context-policy-atom $x) $x)
