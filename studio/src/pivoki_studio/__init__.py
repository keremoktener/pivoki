"""Pivoki's optional interactive editors."""

def launch(paths=(), *, tool=None):
    from .window import Studio
    Studio(paths, tool=tool).mainloop()
    return 0
