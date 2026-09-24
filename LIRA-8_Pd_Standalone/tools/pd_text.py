"""The two line shapes a Pd file is made of."""


def item(kind, x, y, body):
    return "#X %s %d %d %s;" % (kind, x, y, body)


def connect(src, outlet, sink, inlet):
    return "#X connect %d %d %d %d;" % (src, outlet, sink, inlet)
