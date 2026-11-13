"""Three-state header sorting for QTableWidget. Display only.

Qt's setSortingEnabled has no restore step and reorders rows on insert,
so the indicator is painted by hand and rows are moved explicitly.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QTableWidget, QTableWidgetItem

from ..core.table_sort import sorted_positions

# Fill order, stored on column 0. UserRole itself holds the row model.
ORIGINAL_ROLE = int(Qt.UserRole) + 1
HEADER_TOOLTIP = "Klick: A–Z, nochmal Z–A, nochmal Original"


class TableSort:
    """Click cycle: ascending, descending, then the stamped fill order."""

    def __init__(self, table: QTableWidget, kinds: dict[int, str]):
        self._table = table
        self._kinds = dict(kinds)
        self._column: int | None = None
        self._state = 0
        self._busy = False
        header = table.horizontalHeader()
        header.setSectionsClickable(True)
        header.sectionClicked.connect(self._on_section_clicked)
        header.setSortIndicatorShown(False)
        self._install_tooltips()

    def note_original_order(self) -> None:
        """Stamp the current row order and reset the click cycle.

        Call this after a fill, while the rows are still in fill order.
        A later fill (rescan, folder filter) starts the cycle over.
        """
        table = self._table
        table.blockSignals(True)
        try:
            for row in range(table.rowCount()):
                item = table.item(row, 0)
                if item is not None:
                    item.setData(ORIGINAL_ROLE, row)
        finally:
            table.blockSignals(False)
        self._column = None
        self._state = 0
        table.horizontalHeader().setSortIndicatorShown(False)

    def _install_tooltips(self) -> None:
        table = self._table
        for column in self._kinds:
            item = table.horizontalHeaderItem(column)
            if item is None:
                item = QTableWidgetItem()
                table.setHorizontalHeaderItem(column, item)
            item.setToolTip(HEADER_TOOLTIP)
            table.model().setHeaderData(
                column, Qt.Horizontal, HEADER_TOOLTIP, Qt.ToolTipRole
            )

    def _on_section_clicked(self, column: int) -> None:
        if self._busy or column not in self._kinds:
            return
        if column != self._column or self._state == 0:
            new_state = 1
        elif self._state == 1:
            new_state = 2
        else:
            new_state = 0
        self._busy = True
        try:
            order = self._desired_order(column, new_state)
            reorder_rows(self._table, order)
            self._column = column
            self._state = new_state
            self._update_indicator()
        finally:
            self._busy = False

    def _desired_order(self, column: int, state: int) -> list[int]:
        table = self._table
        rows = []
        originals = []
        for row in range(table.rowCount()):
            texts = []
            for col in range(table.columnCount()):
                item = table.item(row, col)
                texts.append("" if item is None else item.text())
            rows.append(texts)
            originals.append(original_row_index(table, row))
        return sorted_positions(rows, originals, column, state, self._kinds[column])

    def _update_indicator(self) -> None:
        header = self._table.horizontalHeader()
        if self._state == 0 or self._column is None:
            header.setSortIndicatorShown(False)
            return
        order = Qt.AscendingOrder if self._state == 1 else Qt.DescendingOrder
        header.setSortIndicator(self._column, order)
        header.setSortIndicatorShown(True)


def original_row_index(table: QTableWidget, row: int) -> int:
    """Stamped fill index for ``row``, or the visual row when none is set."""
    item = table.item(row, 0)
    if item is None:
        return row
    stamped = item.data(ORIGINAL_ROLE)
    if stamped is None:
        return row
    return int(stamped)


def reorder_rows(table: QTableWidget, order: list[int]) -> None:
    """Permute whole rows. Payload, checks, colors, and hidden flags move too."""
    count = table.rowCount()
    if count == 0 or list(order) == list(range(count)):
        return
    if sorted(order) != list(range(count)):
        return

    table.setUpdatesEnabled(False)
    table.blockSignals(True)
    header = table.horizontalHeader()
    header.blockSignals(True)
    try:
        selected = _selected_stamp(table)
        columns = table.columnCount()
        hidden = [table.isRowHidden(row) for row in range(count)]
        taken = [
            [table.takeItem(row, column) for column in range(columns)]
            for row in range(count)
        ]
        for new_row, old_row in enumerate(order):
            for column, item in enumerate(taken[old_row]):
                if item is not None:
                    table.setItem(new_row, column, item)
            table.setRowHidden(new_row, hidden[old_row])
        if selected is not None:
            for row in range(count):
                if original_row_index(table, row) == selected:
                    table.selectRow(row)
                    break
    finally:
        header.blockSignals(False)
        table.blockSignals(False)
        table.setUpdatesEnabled(True)


def _selected_stamp(table: QTableWidget):
    selection = table.selectionModel()
    if selection is None:
        return None
    selected = {index.row() for index in selection.selectedRows()}
    if not selected:
        return None
    current = table.currentRow()
    row = current if current in selected else min(selected)
    return original_row_index(table, row)
