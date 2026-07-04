"""Dark industrial theme for PyQt6 SQLite Workbench.

Obsidian/navy base, teal accent, amber warnings, JetBrains Mono code panes.

Copyright (c) 2026 Leon Priest (7h3v01d). Apache License 2.0.
"""

import re

from PyQt6.QtGui import (
    QColor,
    QFont,
    QSyntaxHighlighter,
    QTextCharFormat,
)
from PyQt6.QtWidgets import QApplication, QStyleFactory

# ----------------------------------------------------------------------------
# Palette
# ----------------------------------------------------------------------------

BG0 = "#0c1117"      # window base
BG1 = "#121a24"      # panels / views
BG2 = "#0a0e14"      # editors / inputs (deepest)
BG3 = "#1a2433"      # hover
BORDER = "#243140"
BORDER_SOFT = "#1b2531"
TEXT = "#ccd7e4"
MUTED = "#7d8fa3"
TEAL = "#2fd6c3"
TEAL_DIM = "#1f9c8f"
TEAL_DEEP = "#123f3a"
AMBER = "#e8a33d"
RED = "#e06c60"
SELECT_BG = "#155048"
ALT_ROW = "#101722"

CODE_FONT_FAMILIES = ["JetBrains Mono", "Cascadia Code", "Consolas", "DejaVu Sans Mono", "monospace"]
UI_FONT_FAMILIES = ["Segoe UI", "Inter", "Ubuntu", "sans-serif"]


def code_font(point_size: int = 10) -> QFont:
    font = QFont()
    font.setFamilies(CODE_FONT_FAMILIES)
    font.setPointSize(point_size)
    return font


# ----------------------------------------------------------------------------
# Stylesheet
# ----------------------------------------------------------------------------

QSS = f"""
* {{
    outline: none;
}}

QMainWindow, QDialog, QMessageBox, QFileDialog {{
    background-color: {BG0};
    color: {TEXT};
}}

QWidget {{
    background-color: {BG0};
    color: {TEXT};
    font-size: 10pt;
    selection-background-color: {SELECT_BG};
    selection-color: {TEXT};
}}

QLabel {{
    background: transparent;
    color: {MUTED};
}}

/* --- Menu bar / menus ------------------------------------------------- */

QMenuBar {{
    background-color: {BG0};
    color: {TEXT};
    border-bottom: 1px solid {BORDER_SOFT};
    padding: 2px 4px;
}}
QMenuBar::item {{
    background: transparent;
    padding: 4px 10px;
    border-radius: 4px;
}}
QMenuBar::item:selected {{
    background-color: {BG3};
    color: {TEAL};
}}
QMenu {{
    background-color: {BG1};
    color: {TEXT};
    border: 1px solid {BORDER};
    padding: 4px;
}}
QMenu::item {{
    padding: 5px 24px 5px 12px;
    border-radius: 4px;
}}
QMenu::item:selected {{
    background-color: {TEAL_DEEP};
    color: {TEAL};
}}
QMenu::separator {{
    height: 1px;
    background: {BORDER_SOFT};
    margin: 4px 8px;
}}

/* --- Toolbar ------------------------------------------------------------ */

QToolBar {{
    background-color: {BG0};
    border-bottom: 1px solid {BORDER_SOFT};
    padding: 3px 4px;
    spacing: 2px;
}}
QToolBar::separator {{
    width: 1px;
    background: {BORDER_SOFT};
    margin: 4px 4px;
}}
QToolButton {{
    background: transparent;
    color: {TEXT};
    border: 1px solid transparent;
    border-radius: 4px;
    padding: 4px 10px;
}}
QToolButton:hover {{
    background-color: {BG3};
    border-color: {BORDER};
    color: {TEAL};
}}
QToolButton:pressed {{
    background-color: {TEAL_DEEP};
}}

/* --- Buttons ------------------------------------------------------------ */

QPushButton {{
    background-color: {BG1};
    color: {TEXT};
    border: 1px solid {BORDER};
    border-radius: 4px;
    padding: 5px 12px;
}}
QPushButton:hover {{
    border-color: {TEAL_DIM};
    color: {TEAL};
    background-color: {BG3};
}}
QPushButton:pressed {{
    background-color: {TEAL_DEEP};
}}
QPushButton:disabled {{
    color: {MUTED};
    border-color: {BORDER_SOFT};
}}

QPushButton#accent {{
    border-color: {TEAL_DIM};
    color: {TEAL};
}}
QPushButton#accent:hover {{
    background-color: {TEAL_DEEP};
    border-color: {TEAL};
}}

QPushButton#danger {{
    color: {RED};
}}
QPushButton#danger:hover {{
    border-color: {RED};
    background-color: #2a1512;
}}

/* --- Inputs ------------------------------------------------------------- */

QLineEdit, QSpinBox, QComboBox {{
    background-color: {BG2};
    color: {TEXT};
    border: 1px solid {BORDER};
    border-radius: 4px;
    padding: 4px 8px;
}}
QLineEdit:focus, QSpinBox:focus, QComboBox:focus {{
    border-color: {TEAL_DIM};
}}
QLineEdit::placeholder {{
    color: {MUTED};
}}
QSpinBox::up-button, QSpinBox::down-button {{
    background-color: {BG1};
    border: none;
    width: 16px;
}}
QSpinBox::up-button:hover, QSpinBox::down-button:hover {{
    background-color: {BG3};
}}
QSpinBox::up-arrow {{
    width: 0; height: 0;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-bottom: 5px solid {MUTED};
}}
QSpinBox::down-arrow {{
    width: 0; height: 0;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 5px solid {MUTED};
}}

/* --- Editors ------------------------------------------------------------ */

QPlainTextEdit {{
    background-color: {BG2};
    color: {TEXT};
    border: 1px solid {BORDER_SOFT};
    border-radius: 4px;
    selection-background-color: {SELECT_BG};
}}

/* --- Tree --------------------------------------------------------------- */

QTreeWidget {{
    background-color: {BG1};
    alternate-background-color: {ALT_ROW};
    border: 1px solid {BORDER_SOFT};
    border-radius: 4px;
}}
QTreeWidget::item {{
    padding: 3px 2px;
    border-radius: 3px;
}}
QTreeWidget::item:hover {{
    background-color: {BG3};
}}
QTreeWidget::item:selected {{
    background-color: {TEAL_DEEP};
    color: {TEAL};
}}
QTreeView::branch {{
    background: transparent;
}}

/* --- Tables ------------------------------------------------------------- */

QTableWidget {{
    background-color: {BG1};
    alternate-background-color: {ALT_ROW};
    gridline-color: {BORDER_SOFT};
    border: 1px solid {BORDER_SOFT};
    border-radius: 4px;
}}
QTableWidget::item {{
    padding: 2px 4px;
}}
QTableWidget::item:selected {{
    background-color: {SELECT_BG};
    color: {TEXT};
}}
QHeaderView {{
    background-color: {BG0};
}}
QHeaderView::section {{
    background-color: {BG0};
    color: {MUTED};
    border: none;
    border-right: 1px solid {BORDER_SOFT};
    border-bottom: 2px solid {TEAL_DIM};
    padding: 5px 8px;
    font-weight: 600;
}}
QHeaderView::section:vertical {{
    border-bottom: 1px solid {BORDER_SOFT};
    border-right: 2px solid {BORDER};
}}
QTableCornerButton::section {{
    background-color: {BG0};
    border: none;
    border-bottom: 2px solid {TEAL_DIM};
}}

/* --- Tabs --------------------------------------------------------------- */

QTabWidget::pane {{
    border: 1px solid {BORDER_SOFT};
    border-radius: 4px;
    top: -1px;
}}
QTabBar::tab {{
    background: transparent;
    color: {MUTED};
    padding: 7px 16px;
    border: none;
    border-bottom: 2px solid transparent;
    margin-right: 2px;
}}
QTabBar::tab:hover {{
    color: {TEXT};
}}
QTabBar::tab:selected {{
    color: {TEAL};
    border-bottom: 2px solid {TEAL};
}}

/* --- Splitter ------------------------------------------------------------ */

QSplitter::handle {{
    background-color: {BG0};
}}
QSplitter::handle:horizontal {{
    width: 5px;
}}
QSplitter::handle:vertical {{
    height: 5px;
}}
QSplitter::handle:hover {{
    background-color: {TEAL_DEEP};
}}

/* --- Status bar ----------------------------------------------------------- */

QStatusBar {{
    background-color: {BG0};
    color: {MUTED};
    border-top: 1px solid {BORDER_SOFT};
}}
QStatusBar::item {{
    border: none;
}}

QLabel#chipMode, QLabel#chipPending {{
    border-radius: 3px;
    padding: 2px 8px;
    font-weight: 600;
    font-size: 9pt;
}}
QLabel#chipMode[mode="off"] {{
    background-color: {BG3};
    color: {MUTED};
}}
QLabel#chipMode[mode="rw"] {{
    background-color: {TEAL_DEEP};
    color: {TEAL};
}}
QLabel#chipMode[mode="ro"] {{
    background-color: #3a2c12;
    color: {AMBER};
}}
QLabel#chipPending[pending="true"] {{
    background-color: #3a2c12;
    color: {AMBER};
}}
QLabel#chipPending[pending="false"] {{
    background-color: {BG3};
    color: {MUTED};
}}

/* --- Scrollbars ------------------------------------------------------------ */

QScrollBar:vertical {{
    background: {BG0};
    width: 10px;
    margin: 0;
}}
QScrollBar::handle:vertical {{
    background: {BORDER};
    border-radius: 5px;
    min-height: 24px;
}}
QScrollBar::handle:vertical:hover {{
    background: {TEAL_DIM};
}}
QScrollBar:horizontal {{
    background: {BG0};
    height: 10px;
    margin: 0;
}}
QScrollBar::handle:horizontal {{
    background: {BORDER};
    border-radius: 5px;
    min-width: 24px;
}}
QScrollBar::handle:horizontal:hover {{
    background: {TEAL_DIM};
}}
QScrollBar::add-line, QScrollBar::sub-line {{
    height: 0; width: 0;
}}
QScrollBar::add-page, QScrollBar::sub-page {{
    background: transparent;
}}

/* --- Message boxes ------------------------------------------------------- */

QMessageBox QLabel {{
    color: {TEXT};
}}
"""


def apply(app: QApplication) -> None:
    """Apply the dark industrial theme to the whole application."""
    fusion = QStyleFactory.create("Fusion")
    if fusion:
        app.setStyle(fusion)
    app.setStyleSheet(QSS)


# ----------------------------------------------------------------------------
# SQL syntax highlighting
# ----------------------------------------------------------------------------

_SQL_KEYWORDS = (
    "ABORT ACTION ADD AFTER ALL ALTER ANALYZE AND AS ASC ATTACH AUTOINCREMENT "
    "BEFORE BEGIN BETWEEN BY CASCADE CASE CAST CHECK COLLATE COLUMN COMMIT "
    "CONFLICT CONSTRAINT CREATE CROSS CURRENT_DATE CURRENT_TIME CURRENT_TIMESTAMP "
    "DATABASE DEFAULT DEFERRABLE DEFERRED DELETE DESC DETACH DISTINCT DROP EACH "
    "ELSE END ESCAPE EXCEPT EXCLUSIVE EXISTS EXPLAIN FAIL FOR FOREIGN FROM FULL "
    "GLOB GROUP HAVING IF IGNORE IMMEDIATE IN INDEX INDEXED INITIALLY INNER "
    "INSERT INSTEAD INTERSECT INTO IS ISNULL JOIN KEY LEFT LIKE LIMIT MATCH "
    "NATURAL NO NOT NOTNULL NULL OF OFFSET ON OR ORDER OUTER PLAN PRAGMA PRIMARY "
    "QUERY RAISE RECURSIVE REFERENCES REGEXP REINDEX RELEASE RENAME REPLACE "
    "RESTRICT RIGHT ROLLBACK ROW ROWID SAVEPOINT SELECT SET TABLE TEMP TEMPORARY "
    "THEN TO TRANSACTION TRIGGER UNION UNIQUE UPDATE USING VACUUM VALUES VIEW "
    "VIRTUAL WHEN WHERE WITH WITHOUT"
).split()

_SQL_FUNCTIONS = (
    "abs avg changes char coalesce count date datetime glob group_concat hex "
    "ifnull instr json json_extract julianday last_insert_rowid length lower "
    "ltrim max min nullif printf quote random randomblob replace round rtrim "
    "strftime substr sum time total total_changes trim typeof unicode upper zeroblob"
).split()


def _fmt(color: str, bold: bool = False, italic: bool = False) -> QTextCharFormat:
    fmt = QTextCharFormat()
    fmt.setForeground(QColor(color))
    if bold:
        fmt.setFontWeight(QFont.Weight.Bold)
    if italic:
        fmt.setFontItalic(True)
    return fmt


class SqlHighlighter(QSyntaxHighlighter):
    """Lightweight SQLite syntax highlighter for QPlainTextEdit documents."""

    def __init__(self, document):
        super().__init__(document)

        keyword_fmt = _fmt(TEAL, bold=True)
        function_fmt = _fmt("#6fb8e8")
        string_fmt = _fmt(AMBER)
        number_fmt = _fmt("#c792ea")
        comment_fmt = _fmt(MUTED, italic=True)
        operator_fmt = _fmt("#8fa8c4")

        self._rules: list[tuple[re.Pattern, QTextCharFormat]] = []

        keyword_pattern = r"\b(?:" + "|".join(_SQL_KEYWORDS) + r")\b"
        self._rules.append((re.compile(keyword_pattern, re.IGNORECASE), keyword_fmt))

        function_pattern = r"\b(?:" + "|".join(_SQL_FUNCTIONS) + r")\b(?=\s*\()"
        self._rules.append((re.compile(function_pattern, re.IGNORECASE), function_fmt))

        self._rules.append((re.compile(r"\b\d+(?:\.\d+)?\b"), number_fmt))
        self._rules.append((re.compile(r"'[^']*'"), string_fmt))
        self._rules.append((re.compile(r'"[^"]*"'), string_fmt))
        self._rules.append((re.compile(r"[=<>!+\-*/%|&~]+"), operator_fmt))
        self._rules.append((re.compile(r"--[^\n]*"), comment_fmt))

        self._comment_fmt = comment_fmt
        self._block_comment_start = re.compile(r"/\*")
        self._block_comment_end = re.compile(r"\*/")

    def highlightBlock(self, text: str) -> None:
        for pattern, fmt in self._rules:
            for match in pattern.finditer(text):
                self.setFormat(match.start(), match.end() - match.start(), fmt)

        # Multi-line /* ... */ comments
        self.setCurrentBlockState(0)
        start = 0
        if self.previousBlockState() != 1:
            m = self._block_comment_start.search(text)
            start = m.start() if m else -1
        if self.previousBlockState() == 1:
            start = 0

        while start >= 0:
            end_match = self._block_comment_end.search(text, start)
            if end_match is None:
                self.setCurrentBlockState(1)
                length = len(text) - start
            else:
                length = end_match.end() - start
            self.setFormat(start, length, self._comment_fmt)
            if end_match is None:
                break
            m = self._block_comment_start.search(text, end_match.end())
            start = m.start() if m else -1
