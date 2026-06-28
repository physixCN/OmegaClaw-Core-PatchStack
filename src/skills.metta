(= (getSkills)
   (py-call (helper.render_capability_context)))


(= (read-file $file)
   (progn (translatePredicate (exists_file $file))
          (translatePredicate (read_file_to_string $file $content ()))
          $content))

(= (write-file $file $str)
   (progn (translatePredicate (open $file write $Out))
          (translatePredicate (write $Out $str))
          (translatePredicate (close $Out))
          WRITE-FILE-SUCCESS))

(= (append-file $file $str)
   (progn (translatePredicate (exists_file $file))
          (translatePredicate (open $file append $Out))
          (translatePredicate (write $Out $str))
          (translatePredicate (nl $Out)),
          (translatePredicate (close $Out))
          APPEND-FILE-SUCCESS))

(= (tavily-search $query)
   (py-call (agentverse.tavily_search $query)))

(= (technical-analysis $ticker)
   (py-call (agentverse.technical_analysis $ticker)))

(= (syntax-error $kind $head $raw $hint)
   (SYNTAX-ERROR $kind $head $raw $hint))

!(import_prolog_functions_from_file (library OmegaClaw-Core ./src/skills.pl) (shell first_char gc read_file_tail))

(= (metta $str)
   (let $code (catch (sread $str))
        (case $code
              (((Error $a $b)
                (syntax-error "invalid-metta-expression" "metta" $str
                              "MeTTa reader could not parse this expression. Use one valid MeTTa expression after metta."))
               ($else
                (let $result (catch (eval $code))
                     (case $result
                           (((Error $ea $eb)
                            (syntax-error "metta-eval-error" "metta" $str
                                           "MeTTa expression parsed, but evaluation failed. Check MeTTa semantics or run a smaller expression."))
                            ($ok (repr (swrite $ok)))))))))))

(= (pin $x)
   PIN-SUCCESS)
