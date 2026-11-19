"""CSV exports of lists: cells a spreadsheet would read as a formula are made plain text, and
long exports are streamed row by row instead of held in memory."""

import csv

FORMULA_STARTS = ("=", "+", "-", "@", "\t", "\r")


def csv_cell(value):
    """The text of one cell; a leading formula character is prefixed with an apostrophe, so a
    spreadsheet shows the value instead of evaluating it."""
    text = "" if value is None else str(value)
    return "'" + text if text.startswith(FORMULA_STARTS) else text


class _Line:
    """A file-like target for csv.writer that hands back each line it is given."""

    def write(self, value):
        return value


def csv_stream(rows):
    """Yield ``rows`` (iterables of values) as CSV lines, every cell through csv_cell."""
    writer = csv.writer(_Line())
    for row in rows:
        yield writer.writerow([csv_cell(value) for value in row])
