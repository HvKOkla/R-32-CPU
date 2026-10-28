"""
Jinrai — parser (descente récursive) et AST.

Grammaire :
  program    := fn*
  fn         := 'naked'? 'fn' ID '(' (ID (',' ID)*)? ')' block
  block      := '{' stmt* '}'
  stmt       := ('let'|'var') ID '=' expr ';'
              | ID '=' expr ';'
              | 'if' expr block ('else' block)?
              | 'while' expr block
              | 'return' expr? ';'
              | 'asm' '(' STR ')' ';'?
  expr       := or_expr
  or_expr    := and_expr ('or' and_expr)*
  and_expr   := cmp_expr ('and' cmp_expr)*
  cmp_expr   := add_expr (('=='|'!='|'<'|'>'|'<='|'>=') add_expr)?
  add_expr   := mul_expr (('+'|'-') mul_expr)*
  mul_expr   := unary (('*'|'/'|'%') unary)*
  unary      := '-' unary | 'not' unary | primary
  primary    := NUM | CHAR | 'true' | 'false' | STR
              | ID ('(' (expr (',' expr)*)? ')')? | '(' expr ')'
"""

from lexer import tokenize, TT_NUM, TT_STR, TT_CHAR, TT_ID, TT_KW, TT_OP, TT_EOF, JinraiError

# --- noeuds AST (tuples taggés, légers) ---
def N(tag, line, **kw):
    d = {"tag": tag, "line": line}
    d.update(kw)
    return d


class Parser:
    def __init__(self, src):
        self.toks = tokenize(src)
        self.pos = 0

    # --- utilitaires tokens ---
    def peek(self, k=0):
        return self.toks[min(self.pos + k, len(self.toks) - 1)]

    def next(self):
        t = self.toks[self.pos]
        self.pos += 1
        return t

    def expect_op(self, op):
        t = self.next()
        if t.kind != TT_OP or t.val != op:
            raise JinraiError("JR0200", f"'{op}' attendu, trouvé {t.val!r}", t.line, t.col)

    def expect_id(self, what="identifiant"):
        t = self.next()
        if t.kind != TT_ID:
            raise JinraiError("JR0201", f"{what} attendu, trouvé {t.val!r}", t.line, t.col)
        return t

    # --- programme ---
    def parse_program(self):
        fns = []
        while self.peek().kind != TT_EOF:
            fns.append(self.parse_fn())
        if not any(f["name"] == "main" for f in fns):
            raise JinraiError("JR0202", "fonction 'main' manquante", 0, 0)
        return N("program", line=0, fns=fns)

    def parse_fn(self):
        t = self.peek()
        naked = False
        if t.kind == TT_KW and t.val == "naked":
            self.next()
            naked = True
        t = self.next()
        if t.kind != TT_KW or t.val != "fn":
            raise JinraiError("JR0203", "'fn' attendu", t.line, t.col)
        name = self.expect_id("nom de fonction").val
        self.expect_op("(")
        params = []
        if not (self.peek().kind == TT_OP and self.peek().val == ")"):
            params.append(self.expect_id("paramètre").val)
            while self.peek().kind == TT_OP and self.peek().val == ",":
                self.next()
                params.append(self.expect_id("paramètre").val)
        self.expect_op(")")
        body = self.parse_block()
        return N("fn", line=t.line, name=name, params=params, body=body, naked=naked)

    def parse_block(self):
        t = self.peek()
        self.expect_op("{")
        stmts = []
        while not (self.peek().kind == TT_OP and self.peek().val == "}"):
            if self.peek().kind == TT_EOF:
                raise JinraiError("JR0204", "bloc non fermé '}'", t.line, t.col)
            stmts.append(self.parse_stmt())
        self.expect_op("}")
        return stmts

    def parse_stmt(self):
        t = self.peek()

        if t.kind == TT_KW and t.val in ("let", "var"):
            self.next()
            name = self.expect_id("nom de variable").val
            self.expect_op("=")
            init = self.parse_expr()
            self.opt_semi()
            return N("decl", line=t.line, name=name, init=init, mutable=(t.val == "var"))

        if t.kind == TT_KW and t.val == "if":
            self.next()
            cond = self.parse_expr()
            then = self.parse_block()
            other = None
            if self.peek().kind == TT_KW and self.peek().val == "else":
                self.next()
                other = self.parse_block()
            return N("if", line=t.line, cond=cond, then=then, other=other)

        if t.kind == TT_KW and t.val == "while":
            self.next()
            cond = self.parse_expr()
            body = self.parse_block()
            return N("while", line=t.line, cond=cond, body=body)

        if t.kind == TT_KW and t.val == "return":
            self.next()
            if self.peek().kind == TT_OP and self.peek().val == ";":
                self.next()
                return N("return", line=t.line, value=None)
            if self.peek().kind == TT_OP and self.peek().val == "}":
                return N("return", line=t.line, value=None)
            value = self.parse_expr()
            self.opt_semi()
            return N("return", line=t.line, value=value)

        if t.kind == TT_KW and t.val == "asm":
            self.next()
            self.expect_op("(")
            s = self.next()
            if s.kind != TT_STR:
                raise JinraiError("JR0205", "asm(\"...\") attendu", s.line, s.col)
            self.expect_op(")")
            if self.peek().kind == TT_OP and self.peek().val == ";":
                self.next()
            return N("asm", line=t.line, text="".join(chr(c) for c in s.val))

        if t.kind == TT_ID:
            nxt = self.peek(1)
            if nxt.kind == TT_OP and nxt.val == "=":
                name = self.next().val
                self.next()  # '='
                value = self.parse_expr()
                self.opt_semi()
                return N("assign", line=t.line, name=name, value=value)

        # appel de fonction / builtin en instruction
        e = self.parse_expr()
        self.opt_semi()
        return N("exprstmt", line=t.line, expr=e)

    def opt_semi(self):
        if self.peek().kind == TT_OP and self.peek().val == ";":
            self.next()

    # --- expressions ---
    def parse_expr(self):
        node = self.parse_and()
        while self.peek().kind == TT_KW and self.peek().val == "or":
            t = self.next()
            node = N("bin", line=t.line, op="or", l=node, r=self.parse_and())
        return node

    def parse_and(self):
        node = self.parse_cmp()
        while self.peek().kind == TT_KW and self.peek().val == "and":
            t = self.next()
            node = N("bin", line=t.line, op="and", l=node, r=self.parse_cmp())
        return node

    def parse_cmp(self):
        node = self.parse_add()
        t = self.peek()
        if t.kind == TT_OP and t.val in ("==", "!=", "<", ">", "<=", ">="):
            self.next()
            node = N("bin", line=t.line, op=t.val, l=node, r=self.parse_add())
        return node

    def parse_add(self):
        node = self.parse_mul()
        while self.peek().kind == TT_OP and self.peek().val in ("+-") :
            t = self.next()
            node = N("bin", line=t.line, op=t.val, l=node, r=self.parse_mul())
        return node

    def parse_mul(self):
        node = self.parse_unary()
        while self.peek().kind == TT_OP and self.peek().val in ("*/%") :
            t = self.next()
            node = N("bin", line=t.line, op=t.val, l=node, r=self.parse_unary())
        return node

    def parse_unary(self):
        t = self.peek()
        if t.kind == TT_OP and t.val == "-":
            self.next()
            return N("un", line=t.line, op="neg", e=self.parse_unary())
        if t.kind == TT_KW and t.val == "not":
            self.next()
            return N("un", line=t.line, op="not", e=self.parse_unary())
        return self.parse_primary()

    def parse_primary(self):
        t = self.next()
        if t.kind == TT_NUM:
            return N("num", line=t.line, val=t.val)
        if t.kind == TT_CHAR:
            return N("num", line=t.line, val=t.val)
        if t.kind == TT_STR:
            return N("str", line=t.line, chars=t.val)
        if t.kind == TT_KW and t.val in ("true", "false"):
            return N("num", line=t.line, val=1 if t.val == "true" else 0)
        if t.kind == TT_ID:
            if self.peek().kind == TT_OP and self.peek().val == "(":
                self.next()
                args = []
                if not (self.peek().kind == TT_OP and self.peek().val == ")"):
                    args.append(self.parse_expr())
                    while self.peek().kind == TT_OP and self.peek().val == ",":
                        self.next()
                        args.append(self.parse_expr())
                self.expect_op(")")
                return N("call", line=t.line, name=t.val, args=args)
            return N("var", line=t.line, name=t.val)
        if t.kind == TT_OP and t.val == "(":
            node = self.parse_expr()
            self.expect_op(")")
            return node
        raise JinraiError("JR0206", f"expression attendue, trouvé {t.val!r}", t.line, t.col)


def parse(src):
    return Parser(src).parse_program()
