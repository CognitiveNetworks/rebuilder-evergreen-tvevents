"""
formatting tools for tabular data
"""

__all__ = ['format_cols', 'format_table']

def format_cols(rows, header=None, right_align=()):
    if not rows:
        return []
    if isinstance(rows[0], dict):
        header = header or sorted(rows[0].keys())
        rows = [[row[h] for h in header] for row in rows]
    if header:
        rows.insert(0, header)
        rows.insert(1, ['-'*len(i) for i in header])
    assert len(set([len(row) for row in rows])) == 1
    rows = [[str(col).strip() for col in row]
            for row in rows]
    lengths = [max([len(row[i]) for row in rows])
               for i in range(len(rows[0]))]
    rows = [[(' '*(length-len(col)) + col) if index in right_align else (col + ' '*(length-len(col)))
             for index, (col, length) in enumerate(zip(row, lengths))]
            for row in rows]
    return rows

def format_table(rows, header=None, right_align=(), joiner=' '):
    """format a table for printing"""
    rows = format_cols(rows, header=header, right_align=right_align)
    return '\n'.join([joiner.join([str(col) for col in row]).rstrip() for row in rows])
