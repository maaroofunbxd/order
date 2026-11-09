# Order

A language for data structures and algorithms that tells you the complexity of
what you just wrote.

```
$ python3 order.py run examples/merge.order

merge_sort
    n = 200      steps = 43,308                stack = 9
    n = 400      steps = 96,200        x2.22   stack = 10
    n = 800      steps = 211,272       x2.20   stack = 11
    n = 1600     steps = 461,012       x2.18   stack = 12

  time   grows like  O(n log n)   (best fit, error 0.9%)
  space  grows like  O(log n)     (best fit, error 1.4%)
         the call stack only -- heap memory is not measured
```

## Why this exists

Python already wins at writing DSA solutions. Dicts, sets, mutable lists and
string indexing are built in, the syntax is terse, and every interviewer reads
it. **A DSA language cannot beat Python at either readability or terseness**,
so if it is going to exist at all it has to win somewhere Python cannot reach.

What Python cannot tell you is the thing DSA is actually about: **how your
solution grows.** You write a nested loop and you work out by hand that it is
O(n²), hoping you are right. You write a binary search and you hope the
boundaries are right.

Order counts the work, runs it at several sizes, fits the measurements
against the standard growth models, and tells you which one you wrote.

All six classes are detected on real code:

| Example | Time | Space (stack) |
|---|---|---|
| `constant.order` — return the first element | `O(1)` | `O(1)` |
| `binary.order` — binary search | `O(log n)` | `O(1)` |
| `linear.order` — linear search, worst case | `O(n)` | `O(1)` |
| `merge.order` — merge sort | `O(n log n)` | `O(log n)` |
| `bubble.order` — bubble sort | `O(n^2)` | `O(1)` |
| `fib.order` — naive fibonacci | `O(2^n)` | `O(n)` |

## How the measurement works

Every expression evaluated increments a counter, and the deepest the call
stack ever got is recorded separately. A measurement runs the function on
inputs of each requested size, records both numbers, and compares them against
`1`, `log n`, `n`, `n log n`, `n²`, `n³`, `2ⁿ`. Each model is scaled by the
constant that fits best through the origin, and the one with the lowest
relative error wins.

That is how `O(n)` and `O(n log n)` get told apart: one of them bends and the
other does not. Fitting `n` to merge sort's numbers fails by 20%+; fitting
`n log n` fails by 0.9%.

The space number is **the call stack, not the heap**. That is the honest limit
of what can be measured without a memory model, and it still separates the
recursive algorithms: bubble sort is `O(1)`, merge sort is `O(log n)`, naive
fibonacci is `O(n)`.

## What is wrong with it

**It is empirical, not a proof.** It reports what your code did on the inputs
you gave it. A branch you never took is invisible. If you add an early exit to
bubble sort so sorted input finishes immediately, the reported order changes —
correctly, but it now depends on the generator, not just the code. The result
is a property of *(code, input generator)*, not of code alone.

**It reports the nearest named class, not the truth.** Naive fibonacci is
really φⁿ ≈ 1.618ⁿ, not 2ⁿ. The fit lands on `O(2^n)` with 17.7% error, which
is the right qualitative answer and visibly the worst fit of the six. The tool
tells you the error so you can see when it is straining.

**Step counts are not time.** They count operations and ignore what each
operation costs. A list `append` and a map lookup both cost one step, which is
a lie about constant factors — but the question DSA asks is about growth, and
constant factors do not change the class.

**Space is only the stack.** Nothing here measures the heap, which is most of
what a space question actually asks. Merge sort's `O(n)` auxiliary array,
quicksort's in-place advantage, a visited-set in graph search — none of it is
visible. And a naive allocation counter would not fix it: it would report
merge sort as `O(n log n)` space, because that is the *total* allocated across
all the merges, when the textbook answer is `O(n)` peak live. Getting that
right needs a reachability walk over live objects, which a tree-walking
interpreter does not have.

**It is slow.** A tree-walking interpreter in Python runs bubble sort at
n=400 in about three seconds. That is why the example stops at 400.

## Design trades against Plain

[Plain](../../plain) bought readability by refusing features. Order is not
trying to be readable, it is trying to be *measured*, so it makes the opposite
trades:

| | Plain | Order |
|---|---|---|
| Types | checked, explicit | dynamic — DSA code is short |
| Mutation | impossible | `xs[i] becomes v`, `append`, `swap` |
| Arguments | named at every call site | positional — `sort(xs)` |
| Precedence | none; mixing is an error | standard — `n * (n - 1) / 2` works |
| Effects | declared and checked | `show` is free |
| The point | a reader trusts the text | the tool tells you the answer |

Same family of ideas, opposite corner of the tradeoff. Neither is better; they
answer different questions.

## Using it

```sh
python3 order.py run   examples/bubble.order
python3 order.py check examples/bubble.order
python3 tests/run_tests.py
python3 order.py run -            # read a program from stdin
```

## The language

```
program <name>

function <name>(<params>):
    <statements>
end

measure <function> with <generator> at <size>, <size>, ...
```

The **generator** is an ordinary function taking one number and returning the
input to measure on. It does not have to return a list — `fib.order` uses one
that just passes `n` through.

**Statements:** `let x be v` · `x becomes v` · `xs[i] becomes v` ·
`m[key] becomes v` · `give v` · `show v` · `if/else/end` · `while/end` ·
`for each x in xs:` · `repeat n times:` · a call.

**Values:** numbers, text, `true`/`false`, `nothing`, lists `[1, 2]`, maps
`{"a": 1}`, sets `{1, 2, 3}`. Sets and maps share braces; a `:` decides.
`set()` makes an empty set, `{}` an empty map.

**Operators:** `+ - * / %`, `== != < > <= >=`, `in`, `and`, `or`, `not`,
indexing, calls.

**Built-ins:** `length` `append` `pop` `insert` `remove_at` `swap` `reverse`
`sort` `sorted` `slice` `copy` `keys` `values` `has` `remove_key` `add`
`discard` `set` `range` `min` `max` `sum` `abs` `floor` `ceil` `text`
`number` `chars` `join` `split` `upper` `lower` `random_list` `sorted_list`
`reversed_list` `random_text`.

Conditions must be `bool` — there is no truthiness, so `while i:` is refused
and you write `while i < n:`. That one rule survived from Plain because it
catches real bugs at no cost.
