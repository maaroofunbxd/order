#!/usr/bin/env python3
"""
Order
=====
A small language for data structures and algorithms that tells you the
complexity of what you just wrote.

Why this exists
---------------
Python already wins at writing DSA solutions: dicts, sets, mutable lists and
string indexing are built in, and the syntax is terse. A DSA language cannot
beat Python at either of those, so it has to win somewhere Python cannot
reach.

What Python cannot tell you is the thing DSA is actually about: **how your
solution grows.** You write a nested loop and you have to work out by hand
that it is O(n^2). You write a binary search and you hope the boundaries are
right.

Order counts the work your program does, runs it at several sizes, fits the
measurements against the standard growth models, and tells you which one you
wrote.

    $ order run bubble.order
    bubble_sort
        n = 100      steps = 10,201
        n = 200      steps = 40,601      x3.98
        n = 400      steps = 162,001     x3.99
        n = 800      steps = 647,001     x3.99

      grows like  O(n^2)          (best fit, error 0.2%)

Design trades against Plain
----------------------------
Plain bought readability by refusing features. Order is not trying to be
readable; it is trying to be *measured*, so it makes the opposite trades:

  * dynamically typed        -- no checker, because DSA code is short
  * mutable lists, maps, sets -- in-place algorithms have to be writable
  * `xs[i] becomes v`         -- indexed assignment
  * positional arguments      -- `sort(xs)` not `sort(items is xs)`
  * standard precedence       -- `n * (n - 1) / 2` has to just work
  * `show` needs no effects   -- printing is not the interesting part here

The measurement is empirical, not a proof. It reports what your code did on
the inputs you gave it. A branch you never triggered is invisible.

Usage:
    python3 order.py run   path/to/program.order
    python3 order.py check path/to/program.order
"""

from __future__ import annotations

import math
import random
import sys
from dataclasses import dataclass, field


# ---------------------------------------------------------------------------
# 1. Errors
# ---------------------------------------------------------------------------

class OrderError(Exception):
    def __init__(self, message, line=None, col=None, hint=None, kind="error"):
        super().__init__(message)
        self.message = message
        self.line = line
        self.col = col
        self.hint = hint
        self.kind = kind


def render_error(err, source, filename):
    lines = source.split("\n")
    out = ["%s: %s: %s" % (filename, err.kind, err.message)]
    if err.line is not None:
        out.append("")
        out.append("  at line %d" % err.line)
        if 1 <= err.line <= len(lines):
            out.append("      " + lines[err.line - 1])
            if err.col:
                out.append("      " + " " * (err.col - 1) + "^")
    if err.hint:
        out.append("")
        out.append("  hint: " + err.hint)
    return "\n".join(out)


# ---------------------------------------------------------------------------
# 2. Tokens and the reader
# ---------------------------------------------------------------------------

KEYWORDS = {
    "program", "function", "end", "measure", "with", "at",
    "let", "be", "becomes", "give", "show",
    "if", "else", "while", "for", "each", "in", "repeat", "times",
    "and", "or", "not", "true", "false", "nothing", "return",
}

SYMBOLS = set("()[]{},:+-*/%<>=!")

TWO_CHAR = {"==", "!=", "<=", ">="}


class Token:
    __slots__ = ("kind", "text", "line", "col", "value")

    def __init__(self, kind, text, line, col, value=None):
        self.kind = kind
        self.text = text
        self.line = line
        self.col = col
        self.value = value


def describe(tok):
    if tok.kind == "NEWLINE":
        return "the end of the line"
    if tok.kind == "EOF":
        return "the end of the file"
    if tok.kind in ("NAME", "NUMBER"):
        return "'%s'" % tok.text
    if tok.kind == "TEXT":
        return "a piece of text"
    return "'%s'" % tok.kind


def tokenize(source):
    tokens = []
    i = 0
    line = 1
    col = 1
    n = len(source)
    depth = 0

    def add(kind, text, ln, cl, value=None):
        tokens.append(Token(kind, text, ln, cl, value))

    while i < n:
        c = source[i]

        if c == "\n":
            if depth == 0:
                add("NEWLINE", "\n", line, col)
            i += 1
            line += 1
            col = 1
            continue

        if c in " \t\r":
            i += 1
            col += 1
            continue

        if c == "#":
            while i < n and source[i] != "\n":
                i += 1
            continue

        if c == '"':
            start_line, start_col = line, col
            i += 1
            col += 1
            buf = []
            while True:
                if i >= n or source[i] == "\n":
                    raise OrderError("this piece of text is never closed",
                                     start_line, start_col,
                                     hint='add a closing double quote')
                ch = source[i]
                if ch == '"':
                    i += 1
                    col += 1
                    break
                if ch == "\\":
                    if i + 1 >= n:
                        raise OrderError("the text ends mid-escape", line, col)
                    nxt = source[i + 1]
                    mapping = {"n": "\n", "t": "\t", '"': '"', "\\": "\\"}
                    if nxt not in mapping:
                        raise OrderError("unknown escape '\\%s'" % nxt, line, col,
                                         hint="allowed: \\n \\t \\\" \\\\")
                    buf.append(mapping[nxt])
                    i += 2
                    col += 2
                    continue
                buf.append(ch)
                i += 1
                col += 1
            add("TEXT", "".join(buf), start_line, start_col, "".join(buf))
            continue

        if c.isdigit():
            start_line, start_col = line, col
            start = i
            while i < n and source[i].isdigit():
                i += 1
                col += 1
            is_float = False
            if i < n and source[i] == "." and i + 1 < n and source[i + 1].isdigit():
                is_float = True
                i += 1
                col += 1
                while i < n and source[i].isdigit():
                    i += 1
                    col += 1
            text = source[start:i]
            value = float(text) if is_float else int(text)
            add("NUMBER", text, start_line, start_col, value)
            continue

        if c.isalpha() or c == "_":
            start_line, start_col = line, col
            start = i
            while i < n and (source[i].isalnum() or source[i] == "_"):
                i += 1
                col += 1
            text = source[start:i]
            add(text if text in KEYWORDS else "NAME", text, start_line, start_col)
            continue

        pair = source[i:i + 2]
        if pair in TWO_CHAR:
            add(pair, pair, line, col)
            i += 2
            col += 2
            continue

        if c in SYMBOLS:
            if c in "([{":
                depth += 1
            elif c in ")]}":
                depth = max(0, depth - 1)
            add(c, c, line, col)
            i += 1
            col += 1
            continue

        raise OrderError("I do not know the character '%s'" % c, line, col)

    add("EOF", "", line, col)
    return tokens


# ---------------------------------------------------------------------------
# 3. Syntax tree
# ---------------------------------------------------------------------------

@dataclass
class Node:
    line: int = 0
    col: int = 0


@dataclass
class Program(Node):
    name: str = ""
    functions: list = field(default_factory=list)
    measures: list = field(default_factory=list)


@dataclass
class FunctionDef(Node):
    name: str = ""
    params: list = field(default_factory=list)
    body: list = field(default_factory=list)


@dataclass
class Measure(Node):
    target: str = ""
    generator: str = ""
    sizes: list = field(default_factory=list)


@dataclass
class LetStmt(Node):
    name: str = ""
    expr: object = None


@dataclass
class AssignStmt(Node):
    target: object = None
    expr: object = None


@dataclass
class GiveStmt(Node):
    expr: object = None


@dataclass
class ShowStmt(Node):
    expr: object = None


@dataclass
class ExprStmt(Node):
    expr: object = None


@dataclass
class IfStmt(Node):
    cond: object = None
    then_block: list = field(default_factory=list)
    else_block: object = None


@dataclass
class WhileStmt(Node):
    cond: object = None
    body: list = field(default_factory=list)


@dataclass
class ForEachStmt(Node):
    var: str = ""
    iterable: object = None
    body: list = field(default_factory=list)


@dataclass
class RepeatStmt(Node):
    count: object = None
    body: list = field(default_factory=list)


@dataclass
class NumLit(Node):
    value: object = 0


@dataclass
class TextLit(Node):
    value: str = ""


@dataclass
class BoolLit(Node):
    value: bool = False


@dataclass
class NothingLit(Node):
    pass


@dataclass
class ListLit(Node):
    items: list = field(default_factory=list)


@dataclass
class MapLit(Node):
    pairs: list = field(default_factory=list)


@dataclass
class SetLit(Node):
    items: list = field(default_factory=list)


@dataclass
class NameExpr(Node):
    name: str = ""


@dataclass
class CallExpr(Node):
    name: str = ""
    args: list = field(default_factory=list)


@dataclass
class IndexExpr(Node):
    target: object = None
    index: object = None


@dataclass
class BinOp(Node):
    op: str = ""
    left: object = None
    right: object = None


@dataclass
class UnaryOp(Node):
    op: str = ""
    expr: object = None


# ---------------------------------------------------------------------------
# 4. Parser
# ---------------------------------------------------------------------------

class Parser:
    def __init__(self, tokens, source):
        self.toks = tokens
        self.pos = 0
        self.source = source

    def peek(self, ahead=0):
        return self.toks[min(self.pos + ahead, len(self.toks) - 1)]

    def at(self, kind):
        return self.peek().kind == kind

    def advance(self):
        tok = self.toks[self.pos]
        if self.pos < len(self.toks) - 1:
            self.pos += 1
        return tok

    def accept(self, kind):
        if self.at(kind):
            return self.advance()
        return None

    def expect(self, kind, after=None):
        if self.at(kind):
            return self.advance()
        tok = self.peek()
        msg = "expected '%s'" % kind
        if after:
            msg += " " + after
        msg += ", but found %s" % describe(tok)
        raise OrderError(msg, tok.line, tok.col)

    def skip_newlines(self):
        while self.at("NEWLINE"):
            self.advance()

    # -- program ------------------------------------------------------------

    def parse_program(self):
        start = self.expect("program")
        name = self.expect("NAME", "after the word 'program'")
        self.expect("NEWLINE", "after the program name")
        functions = []
        measures = []
        self.skip_newlines()
        while not self.at("EOF"):
            if self.at("function"):
                functions.append(self.parse_function())
            elif self.at("measure"):
                measures.append(self.parse_measure())
            else:
                tok = self.peek()
                raise OrderError(
                    "expected 'function' or 'measure', but found %s" % describe(tok),
                    tok.line, tok.col)
            self.skip_newlines()
        return Program(line=start.line, col=start.col, name=name.text,
                       functions=functions, measures=measures)

    def parse_function(self):
        start = self.expect("function")
        name = self.expect("NAME", "after the word 'function'")
        self.expect("(", "after the function name")
        params = []
        if not self.at(")"):
            while True:
                params.append(self.expect("NAME", "as a parameter").text)
                if self.accept(","):
                    continue
                break
        self.expect(")", "to close the parameter list")
        self.expect(":", "after the parameter list")
        body = self.parse_block({"end"})
        self.expect("end", "to close the function '%s'" % name.text)
        return FunctionDef(line=start.line, col=start.col, name=name.text,
                           params=params, body=body)

    def parse_measure(self):
        start = self.expect("measure")
        target = self.expect("NAME", "after the word 'measure'")
        self.expect("with", "after the function being measured")
        generator = self.expect("NAME", "after the word 'with'")
        self.expect("at", "after the generator name")
        sizes = []
        while True:
            tok = self.expect("NUMBER", "as a size to measure at")
            if not isinstance(tok.value, int):
                raise OrderError("a size has to be a whole number",
                                 tok.line, tok.col)
            sizes.append(tok.value)
            if self.accept(","):
                continue
            break
        return Measure(line=start.line, col=start.col, target=target.text,
                       generator=generator.text, sizes=sizes)

    # -- statements ---------------------------------------------------------

    def parse_block(self, stops):
        self.skip_newlines()
        stmts = []
        while True:
            self.skip_newlines()
            if self.peek().kind in stops or self.at("EOF"):
                break
            stmts.append(self.parse_statement())
            if self.at("NEWLINE"):
                self.skip_newlines()
            elif self.peek().kind in stops or self.at("EOF"):
                pass
            else:
                tok = self.peek()
                raise OrderError("found %s after the end of a statement"
                                 % describe(tok), tok.line, tok.col,
                                 hint="each statement goes on its own line")
        return stmts

    def parse_statement(self):
        tok = self.peek()

        if tok.kind == "let":
            self.advance()
            name = self.expect("NAME", "after the word 'let'")
            self.expect("be", "after the name '%s'" % name.text)
            return LetStmt(line=tok.line, col=tok.col, name=name.text,
                           expr=self.parse_expression())

        if tok.kind == "give" or tok.kind == "return":
            self.advance()
            if self.at("NEWLINE") or self.peek().kind in ("end", "else"):
                return GiveStmt(line=tok.line, col=tok.col, expr=None)
            return GiveStmt(line=tok.line, col=tok.col,
                            expr=self.parse_expression())

        if tok.kind == "show":
            self.advance()
            return ShowStmt(line=tok.line, col=tok.col,
                            expr=self.parse_expression())

        if tok.kind == "if":
            self.advance()
            cond = self.parse_expression()
            self.expect(":", "after the condition")
            then_block = self.parse_block({"end", "else"})
            else_block = None
            if self.accept("else"):
                self.expect(":", "after the word 'else'")
                else_block = self.parse_block({"end"})
            self.expect("end", "to close the 'if'")
            return IfStmt(line=tok.line, col=tok.col, cond=cond,
                          then_block=then_block, else_block=else_block)

        if tok.kind == "while":
            self.advance()
            cond = self.parse_expression()
            self.expect(":", "after the 'while' condition")
            body = self.parse_block({"end"})
            self.expect("end", "to close the 'while'")
            return WhileStmt(line=tok.line, col=tok.col, cond=cond, body=body)

        if tok.kind == "for":
            self.advance()
            self.expect("each", "after the word 'for'")
            var = self.expect("NAME", "as the loop name")
            self.expect("in", "after the loop name '%s'" % var.text)
            iterable = self.parse_expression()
            self.expect(":", "after the thing being looped over")
            body = self.parse_block({"end"})
            self.expect("end", "to close the 'for each'")
            return ForEachStmt(line=tok.line, col=tok.col, var=var.text,
                               iterable=iterable, body=body)

        if tok.kind == "repeat":
            self.advance()
            count = self.parse_expression()
            self.expect("times", "after the repeat count")
            self.expect(":", "after the word 'times'")
            body = self.parse_block({"end"})
            self.expect("end", "to close the 'repeat'")
            return RepeatStmt(line=tok.line, col=tok.col, count=count, body=body)

        # An expression, which is either an assignment target or a call.
        expr = self.parse_expression()
        if self.accept("becomes"):
            if not isinstance(expr, (NameExpr, IndexExpr)):
                raise OrderError(
                    "only a name or a place in a list can be changed",
                    expr.line, expr.col,
                    hint="write `x becomes ...` or `xs[i] becomes ...`")
            return AssignStmt(line=expr.line, col=expr.col, target=expr,
                              expr=self.parse_expression())
        if isinstance(expr, CallExpr):
            return ExprStmt(line=expr.line, col=expr.col, expr=expr)
        raise OrderError(
            "this works out a value and then throws it away",
            expr.line, expr.col,
            hint="keep it with `let`, or make it a call")

    # -- expressions --------------------------------------------------------

    def parse_expression(self):
        return self.parse_or()

    def parse_or(self):
        left = self.parse_and()
        while self.at("or"):
            tok = self.advance()
            left = BinOp(line=left.line, col=left.col, op="or",
                         left=left, right=self.parse_and())
        return left

    def parse_and(self):
        left = self.parse_comparison()
        while self.at("and"):
            self.advance()
            left = BinOp(line=left.line, col=left.col, op="and",
                         left=left, right=self.parse_comparison())
        return left

    def parse_comparison(self):
        left = self.parse_additive()
        while self.peek().kind in ("==", "!=", "<", ">", "<=", ">=", "in"):
            op = self.advance()
            left = BinOp(line=left.line, col=left.col, op=op.kind,
                         left=left, right=self.parse_additive())
        return left

    def parse_additive(self):
        left = self.parse_multiplicative()
        while self.peek().kind in ("+", "-"):
            op = self.advance()
            left = BinOp(line=left.line, col=left.col, op=op.kind,
                         left=left, right=self.parse_multiplicative())
        return left

    def parse_multiplicative(self):
        left = self.parse_unary()
        while self.peek().kind in ("*", "/", "%"):
            op = self.advance()
            left = BinOp(line=left.line, col=left.col, op=op.kind,
                         left=left, right=self.parse_unary())
        return left

    def parse_unary(self):
        tok = self.peek()
        if tok.kind == "-":
            self.advance()
            return UnaryOp(line=tok.line, col=tok.col, op="-",
                           expr=self.parse_unary())
        if tok.kind == "not":
            self.advance()
            return UnaryOp(line=tok.line, col=tok.col, op="not",
                           expr=self.parse_unary())
        return self.parse_postfix()

    def parse_postfix(self):
        expr = self.parse_primary()
        while True:
            if self.at("("):
                if not isinstance(expr, NameExpr):
                    tok = self.peek()
                    raise OrderError("only a named function can be called",
                                     tok.line, tok.col)
                expr = self.parse_call(expr)
                continue
            if self.at("["):
                tok = self.advance()
                index = self.parse_expression()
                self.expect("]", "to close the index")
                expr = IndexExpr(line=tok.line, col=tok.col, target=expr,
                                 index=index)
                continue
            break
        return expr

    def parse_call(self, name_expr):
        self.expect("(")
        args = []
        if not self.at(")"):
            while True:
                args.append(self.parse_expression())
                if self.accept(","):
                    continue
                break
        self.expect(")", "to close the call to '%s'" % name_expr.name)
        return CallExpr(line=name_expr.line, col=name_expr.col,
                        name=name_expr.name, args=args)

    def parse_primary(self):
        tok = self.peek()

        if tok.kind == "NUMBER":
            self.advance()
            return NumLit(line=tok.line, col=tok.col, value=tok.value)
        if tok.kind == "TEXT":
            self.advance()
            return TextLit(line=tok.line, col=tok.col, value=tok.value)
        if tok.kind == "true":
            self.advance()
            return BoolLit(line=tok.line, col=tok.col, value=True)
        if tok.kind == "false":
            self.advance()
            return BoolLit(line=tok.line, col=tok.col, value=False)
        if tok.kind == "nothing":
            self.advance()
            return NothingLit(line=tok.line, col=tok.col)
        if tok.kind == "(":
            self.advance()
            inner = self.parse_expression()
            self.expect(")", "to close the group")
            return inner
        if tok.kind == "[":
            self.advance()
            items = []
            if not self.at("]"):
                while True:
                    items.append(self.parse_expression())
                    if self.accept(","):
                        continue
                    break
            self.expect("]", "to close the list")
            return ListLit(line=tok.line, col=tok.col, items=items)
        if tok.kind == "{":
            return self.parse_braces(tok)
        if tok.kind == "NAME":
            self.advance()
            return NameExpr(line=tok.line, col=tok.col, name=tok.text)

        raise OrderError("expected a value, but found %s" % describe(tok),
                         tok.line, tok.col)

    def parse_braces(self, tok):
        self.expect("{")
        if self.accept("}"):
            return MapLit(line=tok.line, col=tok.col, pairs=[])

        first = self.parse_expression()
        if self.accept(":"):
            pairs = [(first, self.parse_expression())]
            while self.accept(","):
                key = self.parse_expression()
                self.expect(":", "after a key")
                pairs.append((key, self.parse_expression()))
            self.expect("}", "to close the map")
            return MapLit(line=tok.line, col=tok.col, pairs=pairs)

        items = [first]
        while self.accept(","):
            if self.at("}"):
                break
            items.append(self.parse_expression())
        self.expect("}", "to close the set")
        return SetLit(line=tok.line, col=tok.col, items=items)


# ---------------------------------------------------------------------------
# 5. Values
# ---------------------------------------------------------------------------

def render(value, nested=False):
    if value is None:
        return "nothing"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if math.isfinite(value) and value == int(value):
            return str(int(value))
        return repr(value)
    if isinstance(value, str):
        if nested:
            escaped = value.replace("\\", "\\\\").replace('"', '\\"')
            return '"%s"' % escaped
        return value
    if isinstance(value, list):
        return "[" + ", ".join(render(v, True) for v in value) + "]"
    if isinstance(value, dict):
        return "{" + ", ".join("%s: %s" % (render(k, True), render(v, True))
                               for k, v in value.items()) + "}"
    if isinstance(value, set):
        if not value:
            return "set()"
        return "{" + ", ".join(sorted(render(v, True) for v in value)) + "}"
    raise AssertionError("cannot show %r" % (value,))


def type_name(value):
    if value is None:
        return "nothing"
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int) or isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "text"
    if isinstance(value, list):
        return "list"
    if isinstance(value, dict):
        return "map"
    if isinstance(value, set):
        return "set"
    return "?"


def is_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


# ---------------------------------------------------------------------------
# 6. Running
# ---------------------------------------------------------------------------

class _GiveSignal(Exception):
    def __init__(self, value):
        self.value = value


class Interpreter:
    def __init__(self, program):
        self.program = program
        self.functions = {fn.name: fn for fn in program.functions}
        self.shadowed = sorted(n for n in self.functions if n in BUILTINS)
        self.steps = 0
        self.depth = 0
        self.max_depth = 0

    # -- entry --------------------------------------------------------------

    def run(self, output=None):
        output = output if output is not None else sys.stdout
        self.output = output
        # Measurements have to be reproducible, or the numbers mean nothing.
        random.seed(20240607)
        for name in self.shadowed:
            sys.stderr.write(
                "note: '%s' is a function you wrote, so the built-in of that "
                "name is not used\n" % name)
        if "main" in self.functions:
            self.call("main", [])
        for measure in self.program.measures:
            self.report_measure(measure)

    def call(self, name, args, where=None):
        if name not in self.functions:
            raise OrderError("there is no function called '%s'" % name,
                             where.line if where else None,
                             where.col if where else None)
        fn = self.functions[name]
        if len(args) != len(fn.params):
            raise OrderError(
                "'%s' takes %d argument%s, but was given %d"
                % (name, len(fn.params), "" if len(fn.params) == 1 else "s",
                   len(args)),
                where.line if where else None,
                where.col if where else None)
        if self.depth > 900:
            raise OrderError(
                "this went too deep -- almost certainly a recursion with no "
                "base case", fn.line, fn.col,
                hint="check that some branch returns before the call")
        scope = dict(zip(fn.params, args))
        self.depth += 1
        if self.depth > self.max_depth:
            self.max_depth = self.depth
        try:
            self.exec_block(fn.body, scope)
            return None
        except _GiveSignal as signal:
            return signal.value
        finally:
            self.depth -= 1

    def exec_block(self, stmts, scope):
        for stmt in stmts:
            self.exec_statement(stmt, scope)

    def exec_statement(self, stmt, scope):
        if isinstance(stmt, LetStmt):
            scope[stmt.name] = self.eval(stmt.expr, scope)
            return
        if isinstance(stmt, AssignStmt):
            value = self.eval(stmt.expr, scope)
            self.assign(stmt.target, value, scope)
            return
        if isinstance(stmt, GiveStmt):
            value = None if stmt.expr is None else self.eval(stmt.expr, scope)
            raise _GiveSignal(value)
        if isinstance(stmt, ShowStmt):
            print(render(self.eval(stmt.expr, scope)), file=self.output)
            return
        if isinstance(stmt, ExprStmt):
            self.eval(stmt.expr, scope)
            return
        if isinstance(stmt, IfStmt):
            if self.truth(self.eval(stmt.cond, scope), stmt.cond):
                self.exec_block(stmt.then_block, scope)
            elif stmt.else_block is not None:
                self.exec_block(stmt.else_block, scope)
            return
        if isinstance(stmt, WhileStmt):
            while self.truth(self.eval(stmt.cond, scope), stmt.cond):
                self.exec_block(stmt.body, scope)
            return
        if isinstance(stmt, ForEachStmt):
            items = self.eval(stmt.iterable, scope)
            for value in self.iterate(items, stmt.iterable):
                scope[stmt.var] = value
                self.exec_block(stmt.body, scope)
            scope.pop(stmt.var, None)
            return
        if isinstance(stmt, RepeatStmt):
            count = self.eval(stmt.count, scope)
            if not is_number(count):
                raise OrderError("`repeat` needs a number of times, not a %s"
                                 % type_name(count), stmt.line, stmt.col)
            for _ in range(int(count)):
                self.exec_block(stmt.body, scope)
            return
        raise AssertionError("unhandled statement %r" % (stmt,))

    def iterate(self, items, where):
        if isinstance(items, (list, str)):
            return list(items)
        if isinstance(items, dict):
            return list(items.keys())
        if isinstance(items, set):
            return sorted(items, key=render)
        raise OrderError("I cannot loop over a %s" % type_name(items),
                         where.line, where.col,
                         hint="loops walk lists, text, maps and sets")

    def truth(self, value, where):
        if isinstance(value, bool):
            return value
        raise OrderError("a condition has to be true or false, not a %s"
                         % type_name(value), where.line, where.col,
                         hint="write the comparison out: `while i < n:`, "
                              "not `while i:`")

    def assign(self, target, value, scope):
        if isinstance(target, NameExpr):
            if target.name not in scope:
                scope[target.name] = value
            else:
                scope[target.name] = value
            return
        container = self.eval(target.target, scope)
        index = self.eval(target.index, scope)
        if isinstance(container, list):
            if not is_number(index):
                raise OrderError("a list is indexed by a number, not a %s"
                                 % type_name(index), target.line, target.col)
            position = int(index)
            if position < 0 or position >= len(container):
                raise OrderError(
                    "there is no position %d in a list of %d"
                    % (position, len(container)), target.line, target.col,
                    hint="positions run from 0 to length - 1")
            container[position] = value
            return
        if isinstance(container, dict):
            container[index] = value
            return
        raise OrderError("I cannot put something inside a %s"
                         % type_name(container), target.line, target.col)

    # -- expressions --------------------------------------------------------

    def eval(self, expr, scope):
        self.steps += 1

        if isinstance(expr, NumLit):
            return expr.value
        if isinstance(expr, TextLit):
            return expr.value
        if isinstance(expr, BoolLit):
            return expr.value
        if isinstance(expr, NothingLit):
            return None
        if isinstance(expr, ListLit):
            return [self.eval(item, scope) for item in expr.items]
        if isinstance(expr, MapLit):
            return {self.eval(k, scope): self.eval(v, scope)
                    for k, v in expr.pairs}
        if isinstance(expr, SetLit):
            return {self.eval(item, scope) for item in expr.items}
        if isinstance(expr, NameExpr):
            if expr.name not in scope:
                if expr.name in self.functions:
                    raise OrderError("'%s' is a function, so it needs ()"
                                     % expr.name, expr.line, expr.col)
                raise OrderError("there is no name '%s' here" % expr.name,
                                 expr.line, expr.col,
                                 hint="create it with `let` before using it")
            return scope[expr.name]
        if isinstance(expr, UnaryOp):
            value = self.eval(expr.expr, scope)
            if expr.op == "-":
                if not is_number(value):
                    raise OrderError("cannot negate a %s" % type_name(value),
                                     expr.line, expr.col)
                return -value
            return not self.truth(value, expr.expr)
        if isinstance(expr, BinOp):
            return self.eval_binop(expr, scope)
        if isinstance(expr, IndexExpr):
            return self.eval_index(expr, scope)
        if isinstance(expr, CallExpr):
            args = [self.eval(a, scope) for a in expr.args]
            return self.eval_call(expr, args)
        raise AssertionError("unhandled expression %r" % (expr,))

    def eval_index(self, expr, scope):
        container = self.eval(expr.target, scope)
        index = self.eval(expr.index, scope)

        if isinstance(container, (list, str)):
            if not is_number(index):
                raise OrderError("a %s is indexed by a number, not a %s"
                                 % (type_name(container), type_name(index)),
                                 expr.line, expr.col)
            position = int(index)
            if position < 0 or position >= len(container):
                raise OrderError(
                    "there is no position %d in a %s of %d"
                    % (position, type_name(container), len(container)),
                    expr.line, expr.col,
                    hint="positions run from 0 to length - 1")
            return container[position]
        if isinstance(container, dict):
            if index not in container:
                raise OrderError("this map has no key %s" % render(index, True),
                                 expr.line, expr.col,
                                 hint="check first with `has(map, key)`")
            return container[index]
        raise OrderError("I cannot look inside a %s" % type_name(container),
                         expr.line, expr.col)

    def eval_binop(self, expr, scope):
        op = expr.op

        if op == "and":
            left = self.truth(self.eval(expr.left, scope), expr.left)
            if not left:
                return False
            return self.truth(self.eval(expr.right, scope), expr.right)
        if op == "or":
            left = self.truth(self.eval(expr.left, scope), expr.left)
            if left:
                return True
            return self.truth(self.eval(expr.right, scope), expr.right)

        left = self.eval(expr.left, scope)
        right = self.eval(expr.right, scope)

        if op == "+":
            if is_number(left) and is_number(right):
                return left + right
            if isinstance(left, str) and isinstance(right, str):
                return left + right
            if isinstance(left, list) and isinstance(right, list):
                return left + right
            raise OrderError("cannot add a %s to a %s"
                             % (type_name(left), type_name(right)),
                             expr.line, expr.col)
        if op in ("-", "*", "/", "%"):
            if not (is_number(left) and is_number(right)):
                raise OrderError("'%s' works on numbers, but got a %s and a %s"
                                 % (op, type_name(left), type_name(right)),
                                 expr.line, expr.col)
            if op == "-":
                return left - right
            if op == "*":
                return left * right
            if op == "%":
                if right == 0:
                    raise OrderError("cannot take a remainder by zero",
                                     expr.line, expr.col)
                return left % right
            if right == 0:
                raise OrderError("cannot divide by zero", expr.line, expr.col)
            return left / right
        if op == "in":
            return self.member(right, left, expr)
        if op in ("==", "!="):
            same = left == right
            return same if op == "==" else not same
        if op in ("<", ">", "<=", ">="):
            if is_number(left) and is_number(right):
                pass
            elif isinstance(left, str) and isinstance(right, str):
                pass
            else:
                raise OrderError("cannot compare a %s with a %s"
                                 % (type_name(left), type_name(right)),
                                 expr.line, expr.col)
            if op == "<":
                return left < right
            if op == ">":
                return left > right
            if op == "<=":
                return left <= right
            return left >= right

        raise AssertionError("unhandled operator %r" % op)

    def member(self, container, value, where):
        if isinstance(container, (list, str)):
            return value in container
        if isinstance(container, dict):
            return value in container
        if isinstance(container, set):
            return value in container
        raise OrderError("I cannot look inside a %s" % type_name(container),
                         where.line, where.col)

    def eval_call(self, expr, args):
        # Your own function wins over a built-in with the same name.  Your
        # file is right in front of you; the built-in is not.
        if expr.name in self.functions:
            return self.call(expr.name, args, expr)
        if expr.name in BUILTINS:
            arity, fn = BUILTINS[expr.name]
            if arity >= 0 and len(args) != arity:
                raise OrderError(
                    "'%s' is a built-in taking %d argument%s, but was given %d"
                    % (expr.name, arity, "" if arity == 1 else "s", len(args)),
                    expr.line, expr.col)
            return fn(self, args, expr)
        raise OrderError("there is no function called '%s'" % expr.name,
                         expr.line, expr.col)

    # -- measurement --------------------------------------------------------

    def measure_one(self, fn_name, generator, size):
        if generator not in self.functions:
            raise OrderError("there is no generator function called '%s'"
                             % generator)
        data = self.call(generator, [size])
        self.steps = 0
        self.max_depth = 0
        self.call(fn_name, [data])
        return self.steps, self.max_depth

    def report_measure(self, measure):
        if measure.target not in self.functions:
            raise OrderError("there is no function called '%s' to measure"
                             % measure.target)
        if measure.generator not in self.functions:
            raise OrderError("there is no function called '%s' to make inputs"
                             % measure.generator)

        rows = []
        for size in measure.sizes:
            steps, depth = self.measure_one(measure.target,
                                            measure.generator, size)
            rows.append((size, steps, depth))

        print("", file=self.output)
        print(measure.target, file=self.output)

        previous = None
        for size, steps, depth in rows:
            ratio = ""
            if previous is not None and previous > 0:
                ratio = "x%.2f" % (steps / previous)
            print("    n = %-8d steps = %-13s %-7s stack = %d"
                  % (size, "{:,}".format(steps), ratio, depth),
                  file=self.output)
            previous = steps

        time_order, time_error = best_fit([(n, s) for n, s, _ in rows])
        space_order, space_error = best_fit([(n, d) for n, _, d in rows])

        print("", file=self.output)
        print("  time   grows like  %-12s (best fit, error %.1f%%)"
              % (time_order, time_error * 100), file=self.output)
        print("  space  grows like  %-12s (best fit, error %.1f%%)"
              % (space_order, space_error * 100), file=self.output)
        print("         the call stack only -- heap memory is not measured",
              file=self.output)
        print("", file=self.output)


# ---------------------------------------------------------------------------
# 7. Growth models
# ---------------------------------------------------------------------------

def _safe(fn):
    def wrapped(n):
        try:
            return float(fn(n))
        except (OverflowError, ValueError):
            return float("inf")
    return wrapped


MODELS = [
    ("O(1)", _safe(lambda n: 1)),
    ("O(log n)", _safe(lambda n: math.log2(n) if n > 1 else 1)),
    ("O(n)", _safe(lambda n: n)),
    ("O(n log n)", _safe(lambda n: n * math.log2(n) if n > 1 else 1)),
    ("O(n^2)", _safe(lambda n: n * n)),
    ("O(n^3)", _safe(lambda n: n ** 3)),
    ("O(2^n)", _safe(lambda n: 2 ** n)),
]


def best_fit(rows):
    """Fit each growth model to the measurements and pick the closest.

    Each model is scaled by the constant that fits best through the origin,
    then compared by total relative error.  This is how you tell `O(n)` from
    `O(n log n)` without guessing: one of them bends and the other does not.
    """
    if len(rows) < 2:
        return ("unknown", 1.0)

    sizes = [float(n) for n, _ in rows]
    steps = [float(s) for _, s in rows]
    total = sum(steps) or 1.0

    best = None
    for name, model in MODELS:
        predicted = [model(n) for n in sizes]
        if any(not math.isfinite(p) for p in predicted):
            continue
        denominator = sum(p * p for p in predicted)
        if denominator == 0:
            continue
        scale = sum(p * s for p, s in zip(predicted, steps)) / denominator
        error = sum(abs(scale * p - s) for p, s in zip(predicted, steps)) / total
        if best is None or error < best[1]:
            best = (name, error)

    if best is None:
        return ("unknown", 1.0)
    return best


# ---------------------------------------------------------------------------
# 8. Built-ins
# ---------------------------------------------------------------------------

def need(args, index, kinds, fn_name, where):
    value = args[index]
    if not isinstance(value, kinds) or isinstance(value, bool):
        raise OrderError(
            "'%s' wanted a %s as argument %d, but got a %s"
            % (fn_name, " or ".join(k.__name__ for k in kinds), index + 1,
               type_name(value)),
            where.line, where.col)
    return value


def need_number(args, index, fn_name, where):
    value = args[index]
    if not is_number(value):
        raise OrderError("'%s' wanted a number as argument %d, but got a %s"
                         % (fn_name, index + 1, type_name(value)),
                         where.line, where.col)
    return value


def need_position(container, index, fn_name, where):
    if not is_number(index):
        raise OrderError("'%s' wanted a number position, but got a %s"
                         % (fn_name, type_name(index)), where.line, where.col)
    position = int(index)
    if position < 0 or position >= len(container):
        raise OrderError("there is no position %d (length is %d)"
                         % (position, len(container)), where.line, where.col)
    return position


def b_length(interp, args, where):
    value = args[0]
    if isinstance(value, (list, str, dict, set)):
        return len(value)
    raise OrderError("'length' wanted a list, text, map or set, but got a %s"
                     % type_name(value), where.line, where.col)


def b_append(interp, args, where):
    items = need(args, 0, (list,), "append", where)
    items.append(args[1])
    return None


def b_pop(interp, args, where):
    items = need(args, 0, (list,), "pop", where)
    if not items:
        raise OrderError("cannot pop from an empty list", where.line, where.col)
    return items.pop()


def b_insert(interp, args, where):
    items = need(args, 0, (list,), "insert", where)
    position = need_number(args, 1, "insert", where)
    items.insert(int(position), args[2])
    return None


def b_remove_at(interp, args, where):
    items = need(args, 0, (list,), "remove_at", where)
    position = need_position(items, args[1], "remove_at", where)
    return items.pop(position)


def b_swap(interp, args, where):
    items = need(args, 0, (list,), "swap", where)
    i = need_position(items, args[1], "swap", where)
    j = need_position(items, args[2], "swap", where)
    items[i], items[j] = items[j], items[i]
    return None


def b_reverse(interp, args, where):
    items = need(args, 0, (list,), "reverse", where)
    items.reverse()
    return None


def b_sort(interp, args, where):
    items = need(args, 0, (list,), "sort", where)
    items.sort()
    return None


def b_sorted(interp, args, where):
    items = need(args, 0, (list,), "sorted", where)
    return sorted(items)


def b_slice(interp, args, where):
    items = args[0]
    if not isinstance(items, (list, str)):
        raise OrderError("'slice' wanted a list or text, but got a %s"
                         % type_name(items), where.line, where.col)
    start = int(need_number(args, 1, "slice", where))
    end = int(need_number(args, 2, "slice", where))
    return items[start:end]


def b_copy(interp, args, where):
    value = args[0]
    if isinstance(value, list):
        return list(value)
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, set):
        return set(value)
    return value


def b_keys(interp, args, where):
    return list(need(args, 0, (dict,), "keys", where).keys())


def b_values(interp, args, where):
    return list(need(args, 0, (dict,), "values", where).values())


def b_has(interp, args, where):
    container = args[0]
    key = args[1]
    if isinstance(container, dict):
        return key in container
    if isinstance(container, set):
        return key in container
    if isinstance(container, (list, str)):
        return key in container
    raise OrderError("'has' wanted a map, set, list or text, but got a %s"
                     % type_name(container), where.line, where.col)


def b_remove_key(interp, args, where):
    mapping = need(args, 0, (dict,), "remove_key", where)
    mapping.pop(args[1], None)
    return None


def b_add(interp, args, where):
    target = args[0]
    if isinstance(target, set):
        target.add(args[1])
        return None
    if isinstance(target, list):
        target.append(args[1])
        return None
    raise OrderError("'add' wanted a set or list, but got a %s"
                     % type_name(target), where.line, where.col)


def b_discard(interp, args, where):
    target = need(args, 0, (set,), "discard", where)
    target.discard(args[1])
    return None


def b_empty_set(interp, args, where):
    return set()


def b_range(interp, args, where):
    if len(args) == 1:
        stop = int(need_number(args, 0, "range", where))
        return list(range(stop))
    start = int(need_number(args, 0, "range", where))
    stop = int(need_number(args, 1, "range", where))
    return list(range(start, stop))


def b_min(interp, args, where):
    items = need(args, 0, (list,), "min", where)
    if not items:
        raise OrderError("cannot take the smallest of an empty list",
                         where.line, where.col)
    return min(items)


def b_max(interp, args, where):
    items = need(args, 0, (list,), "max", where)
    if not items:
        raise OrderError("cannot take the largest of an empty list",
                         where.line, where.col)
    return max(items)


def b_sum(interp, args, where):
    items = need(args, 0, (list,), "sum", where)
    return sum(items)


def b_abs(interp, args, where):
    return abs(need_number(args, 0, "abs", where))


def b_floor(interp, args, where):
    return int(math.floor(need_number(args, 0, "floor", where)))


def b_ceil(interp, args, where):
    return int(math.ceil(need_number(args, 0, "ceil", where)))


def b_text(interp, args, where):
    return render(args[0])


def b_number(interp, args, where):
    value = need(args, 0, (str,), "number", where)
    try:
        stripped = value.strip()
        return float(stripped) if "." in stripped else int(stripped)
    except ValueError:
        raise OrderError("'%s' is not a number" % value, where.line, where.col)


def b_chars(interp, args, where):
    return list(need(args, 0, (str,), "chars", where))


def b_join(interp, args, where):
    items = need(args, 0, (list,), "join", where)
    separator = need(args, 1, (str,), "join", where)
    return separator.join(render(v) for v in items)


def b_split(interp, args, where):
    value = need(args, 0, (str,), "split", where)
    separator = need(args, 1, (str,), "split", where)
    return value.split(separator)


def b_upper(interp, args, where):
    return need(args, 0, (str,), "upper", where).upper()


def b_lower(interp, args, where):
    return need(args, 0, (str,), "lower", where).lower()


def b_random_list(interp, args, where):
    size = int(need_number(args, 0, "random_list", where))
    low = int(need_number(args, 1, "random_list", where))
    high = int(need_number(args, 2, "random_list", where))
    return [random.randint(low, high) for _ in range(size)]


def b_sorted_list(interp, args, where):
    size = int(need_number(args, 0, "sorted_list", where))
    return list(range(size))


def b_reversed_list(interp, args, where):
    size = int(need_number(args, 0, "reversed_list", where))
    return list(range(size, 0, -1))


def b_random_text(interp, args, where):
    size = int(need_number(args, 0, "random_text", where))
    return "".join(random.choice("abcdefghijklmnopqrstuvwxyz")
                   for _ in range(size))


# name -> (arity, implementation).  -1 means "any number of arguments".
BUILTINS = {
    "length":       (1, b_length),
    "append":       (2, b_append),
    "pop":          (1, b_pop),
    "insert":       (3, b_insert),
    "remove_at":    (2, b_remove_at),
    "swap":         (3, b_swap),
    "reverse":      (1, b_reverse),
    "sort":         (1, b_sort),
    "sorted":       (1, b_sorted),
    "slice":        (3, b_slice),
    "copy":         (1, b_copy),
    "keys":         (1, b_keys),
    "values":       (1, b_values),
    "has":          (2, b_has),
    "remove_key":   (2, b_remove_key),
    "add":          (2, b_add),
    "discard":      (2, b_discard),
    "set":          (0, b_empty_set),
    "range":        (-1, b_range),
    "min":          (1, b_min),
    "max":          (1, b_max),
    "sum":          (1, b_sum),
    "abs":          (1, b_abs),
    "floor":        (1, b_floor),
    "ceil":         (1, b_ceil),
    "text":         (1, b_text),
    "number":       (1, b_number),
    "chars":        (1, b_chars),
    "join":         (2, b_join),
    "split":        (2, b_split),
    "upper":        (1, b_upper),
    "lower":        (1, b_lower),
    "random_list":  (3, b_random_list),
    "sorted_list":  (1, b_sorted_list),
    "reversed_list": (1, b_reversed_list),
    "random_text":  (1, b_random_text),
}


# ---------------------------------------------------------------------------
# 9. Command line
# ---------------------------------------------------------------------------

USAGE = """Order

  python3 order.py run   path/to/program.order
  python3 order.py check path/to/program.order

A program is a list of functions, then any number of measurements:

  function bubble(numbers):
      ...
  end

  measure bubble with random_list at 100, 200, 400, 800

`measure` runs the function on inputs of each size, counts the work it does,
and reports which growth curve it follows.

The measurement is empirical: it is what your code did on those inputs, not
a proof.  A branch you never took is invisible to it.
"""


def load(path):
    if path == "-":
        source = sys.stdin.read()
        return source, "<stdin>"
    with open(path, "r") as handle:
        return handle.read(), path


def main(argv):
    if len(argv) < 3 or argv[1] not in ("run", "check"):
        sys.stderr.write(USAGE)
        return 2

    command, path = argv[1], argv[2]

    try:
        source, shown = load(path)
    except FileNotFoundError:
        sys.stderr.write("there is no file called %s\n" % path)
        return 2

    try:
        program = Parser(tokenize(source), source).parse_program()
        interpreter = Interpreter(program)

        if command == "check":
            names = {fn.name for fn in program.functions}
            for measure in program.measures:
                for needed in (measure.target, measure.generator):
                    if needed not in names:
                        raise OrderError(
                            "`measure` names '%s', but no such function exists"
                            % needed, measure.line, measure.col)
            print("%s: reads clearly" % shown)
            return 0

        interpreter.run()
    except OrderError as err:
        sys.stderr.write(render_error(err, source, shown) + "\n")
        return 1
    except RecursionError:
        sys.stderr.write(
            "%s: this went too deep -- almost certainly a recursion with no "
            "base case\n" % shown)
        return 1
    return 0


if __name__ == "__main__":
    sys.setrecursionlimit(20000)
    sys.exit(main(sys.argv))
