"""
Jinrai — lexer (découpage du source .jr en tokens).
"""

KEYWORDS = {
    "fn", "let", "var", "if", "else", "while", "return",
    "asm", "naked", "true", "false", "and", "or", "not",
}

TT_NUM, TT_STR, TT_CHAR, TT_ID, TT_KW, TT_OP, TT_EOF = range(7)

ESCAPES = {"n": 10, "r": 13, "t": 9, "0": 0, "\\": 92, '"': 34, "'": 39}


class Tok:
    __slots__ = ("kind", "val", "line", "col")

    def __init__(self, kind, val, line, col):
        self.kind, self.val, self.line, self.col = kind, val, line, col

    def __repr__(self):
        return f"Tok({self.kind},{self.val!r} @{self.line}:{self.col})"


class JinraiError(Exception):
    """Erreur Jinrai avec position source."""

    def __init__(self, code, msg, line=0, col=0):
        self.code, self.msg, self.line, self.col = code, msg, line, col
        super().__init__(str(self))

    def __str__(self):
        pos = f"  --> source.jr:{self.line}:{self.col}\n" if self.line else ""
        return f"erreur[{self.code}] : {self.msg}\n{pos}"


def _read_escape(src, i, line, col):
    if i >= len(src):
        raise JinraiError("JR0100", "échappement incomplet", line, col)
    c = src[i]
    if c in ESCAPES:
        return ESCAPES[c], i + 1
    raise JinraiError("JR0101", f"échappement inconnu \\{c}", line, col)


def tokenize(src):
    toks = []
    i, line, col = 0, 1, 1
    n = len(src)

    def advance(k=1):
        nonlocal i, line, col
        for _ in range(k):
            if src[i] == "\n":
                line += 1
                col = 1
            else:
                col += 1
            i += 1

    while i < n:
        c = src[i]

        if c in " \t\r":
            advance()
        elif c == "\n":
            advance()
        elif c == "/" and i + 1 < n and src[i + 1] == "/":
            while i < n and src[i] != "\n":
                advance()
        elif c == "/" and i + 1 < n and src[i + 1] == "*":
            advance(2)
            while i + 1 < n and not (src[i] == "*" and src[i + 1] == "/"):
                advance()
            if i + 1 >= n:
                raise JinraiError("JR0102", "commentaire /* */ non fermé", line, col)
            advance(2)
        elif c.isdigit():
            sl, sc = line, col
            j = i
            if src[j:j + 2].lower() == "0x":
                j += 2
                while j < n and (src[j].isdigit() or src[j].lower() in "abcdef"):
                    j += 1
                val = int(src[i + 2:j], 16)
            elif src[j:j + 2].lower() == "0b":
                j += 2
                while j < n and src[j] in "01":
                    j += 1
                val = int(src[i + 2:j], 2)
            else:
                while j < n and src[j].isdigit():
                    j += 1
                val = int(src[i:j], 10)
            toks.append(Tok(TT_NUM, val, sl, sc))
            advance(j - i)
        elif c == '"':
            sl, sc = line, col
            advance()
            chars = []
            while i < n and src[i] != '"':
                if src[i] == "\\":
                    advance()
                    v, ni = _read_escape(src, i, line, col)
                    chars.append(v)
                    advance(ni - i)
                else:
                    chars.append(ord(src[i]))
                    advance()
            if i >= n:
                raise JinraiError("JR0103", "chaîne non fermée", sl, sc)
            advance()
            toks.append(Tok(TT_STR, chars, sl, sc))
        elif c == "'":
            sl, sc = line, col
            advance()
            if i < n and src[i] == "\\":
                advance()
                v, ni = _read_escape(src, i, line, col)
                advance(ni - i)
            elif i < n:
                v = ord(src[i])
                advance()
            else:
                raise JinraiError("JR0104", "caractère incomplet", sl, sc)
            if i >= n or src[i] != "'":
                raise JinraiError("JR0104", "caractère non fermé", sl, sc)
            advance()
            toks.append(Tok(TT_CHAR, v, sl, sc))
        elif c.isalpha() or c == "_":
            sl, sc = line, col
            j = i
            while j < n and (src[j].isalnum() or src[j] == "_"):
                j += 1
            word = src[i:j]
            toks.append(Tok(TT_KW if word in KEYWORDS else TT_ID, word, sl, sc))
            advance(j - i)
        elif src[i:i + 2] in ("<=", ">=", "==", "!="):
            toks.append(Tok(TT_OP, src[i:i + 2], line, col))
            advance(2)
        elif c in "+-*/%(){}[],;=<>":
            toks.append(Tok(TT_OP, c, line, col))
            advance()
        else:
            raise JinraiError("JR0105", f"caractère inattendu {c!r}", line, col)

    toks.append(Tok(TT_EOF, None, line, col))
    return toks
