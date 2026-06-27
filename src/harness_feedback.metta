; Patch 3: tiny MeTTa-owned skill result telemetry.
;
; Payload transport stays on the existing COMMAND_RETURN path. This layer only
; adds a fixed-width semantic status atom: (SKILL_RESULT command status).

(SkillResultStatus success)
(SkillResultStatus empty)
(SkillResultStatus rejected)
(SkillResultStatus failed)
(SkillResultStatus timeout)

(CommandShape remember)
(CommandShape query)
(CommandShape episodes)
(CommandShape pin)
(CommandShape shell)
(CommandShape read-file)
(CommandShape write-file)
(CommandShape append-file)
(CommandShape send)
(CommandShape search)
(CommandShape tavily-search)
(CommandShape technical-analysis)
(CommandShape metta)
(CommandShape syntax-error)
(CommandShape unknown)

(= (skill-result-command-shape $command)
   (let $shapeText (py-call (helper.describe_command_shape (swrite $command)))
        (case (catch (sread $shapeText)) (((Error $a $b) (CommandShape unknown))
                                         ($shape $shape)))))

(= (skill-result-command-head (CommandShape $head)) $head)

(= (skill-result-empty-status $shape)
   (case $shape (((CommandShape query) empty)
                 ((CommandShape episodes) empty)
                 ((CommandShape search) empty)
                 ((CommandShape tavily-search) empty)
                 ((CommandShape technical-analysis) empty)
                 ((CommandShape $head) success))))

(= (skill-result-status $shape $result)
   (case $result (((SYNTAX-ERROR $a $b $c $d) rejected)
                  (WRITE-FILE-SUCCESS success)
                  (APPEND-FILE-SUCCESS success)
                  (REMEMBER-SUCCESS success)
                  (PIN-SUCCESS success)
                  (SEND-DELIVERED success)
                  (timeout_error timeout)
                  (() (skill-result-empty-status $shape))
                  ((Error $a $b) failed)
                  ($else success))))

(= (skill-result-atom $shape $result)
   (SKILL_RESULT (skill-result-command-head $shape) (skill-result-status $shape $result)))

(= (feedback-send-command-items $command)
   (let $_ (catch (eval $command))
        (superpose ((COMMAND_RETURN: ($command "SEND-DELIVERED"))
                    (SKILL_RESULT send success)))))

(= (feedback-normal-command-items $shape $command)
   (let $evalResult (catch (let $R (eval $command)
                                (CommandEval $R (py-call (helper.normalize_string $R)))))
        (case $evalResult (((CommandEval $raw $normalized)
                            (let $_ (HandleError SINGLE_COMMAND_FORMAT_ERROR_NOTHING_WAS_DONE_PLEASE_FIX_AND_RETRY $command $raw)
                                 (superpose ((COMMAND_RETURN: ($command $normalized))
                                             (skill-result-atom $shape $raw)))))
                           ((Error $a $b)
                            (let $_ (HandleError SINGLE_COMMAND_FORMAT_ERROR_NOTHING_WAS_DONE_PLEASE_FIX_AND_RETRY $command (Error $a $b))
                                 (superpose ((COMMAND_RETURN: ($command (Error $a $b)))
                                             (skill-result-atom $shape (Error $a $b))))))))))

(= (feedback-command-items $shape $command)
   (case $shape (((CommandShape send) (feedback-send-command-items $command))
                 ($else (feedback-normal-command-items $shape $command)))))

(= (feedback-eval-command $command)
   (let $shape (skill-result-command-shape $command)
        (feedback-command-items $shape $command)))

(= (feedback-eval-results $sexpr)
   (RESULTS: (collapse (let $command (superpose $sexpr) (feedback-eval-command $command)))))

(= (feedback-render-lastresults (RESULTS: $items) $previous)
   (if (== $items ())
       $previous
       (string-safe (repr (RESULTS: $items)))))

(= (feedback-debug-results (RESULTS: $items))
   (SKILL_RESULTS: (collapse (let $item (superpose $items)
                                  (case $item (((SKILL_RESULT $head $status) $item)
                                               ($else empty)))))))
