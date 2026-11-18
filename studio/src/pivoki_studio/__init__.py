"""Pivoki's optional interactive editors."""

def launch(paths=()):
    from .window import Studio
    Studio(paths).mainloop()
    return 0
