import csv
import re
import sqlite3
import sys
import traceback
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

from PyQt6.QtCore import Qt, QSettings, QPoint
from PyQt6.QtGui import QAction, QKeySequence
from PyQt6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QSplitter,
    QStatusBar,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QToolBar,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

import theme


APP_NAME = "SQLite Workbench"
ORG_NAME = "LocalTools"

NULL_TOKEN = "<NULL>"


def quote_ident(identifier: str) -> str:
    """Safely quote a SQLite identifier."""
    return '"' + identifier.replace('"', '""') + '"'


def display_value(value) -> str:
    if value is None:
        return NULL_TOKEN
    if isinstance(value, bytes):
        return f"<BLOB {len(value)} bytes>"
    return str(value)


def sqlite_uri_readonly(path: str) -> str:
    resolved = Path(path).resolve().as_posix()
    return f"file:{quote(resolved, safe='/:')}?mode=ro"


def is_probably_query(sql: str) -> bool:
    m = re.match(r"\s*(?:--.*\n\s*)*(\w+)", sql, re.IGNORECASE)
    if not m:
        return False
    first = m.group(1).lower()
    return first in {"select", "with", "pragma", "explain"}


def is_probably_write(sql: str) -> bool:
    return not is_probably_query(sql)


class SqliteWorkbench(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.resize(1350, 850)

        self.settings = QSettings(ORG_NAME, APP_NAME)

        self.conn: sqlite3.Connection | None = None
        self.db_path: str | None = None
        self.read_only = False
        self.pending_changes = False

        self.current_object_name: str | None = None
        self.current_object_type: str | None = None
        self.current_columns: list[str] = []
        self.current_column_types: dict[str, str] = {}
        self.current_pk_cols: list[str] = []
        self.current_key_mode: str | None = None
        self.original_rows: list[dict] = []
        self.new_row_numbers: set[int] = set()
        self.loading_table = False
        self.current_sql_file: str | None = None

        self._build_ui()
        self._build_actions()
        self._restore_settings()

    def _build_ui(self):
        self.status = QStatusBar()
        self.setStatusBar(self.status)

        self.mode_chip = QLabel("NO DB")
        self.mode_chip.setObjectName("chipMode")
        self.pending_chip = QLabel("CLEAN")
        self.pending_chip.setObjectName("chipPending")
        self.status.addPermanentWidget(self.pending_chip)
        self.status.addPermanentWidget(self.mode_chip)
        self._update_chips()

        self.schema_tree = QTreeWidget()
        self.schema_tree.setHeaderLabels(["Database objects"])
        self.schema_tree.setAlternatingRowColors(True)
        self.schema_tree.itemSelectionChanged.connect(self.on_schema_selection_changed)

        self.ddl_view = QPlainTextEdit()
        self.ddl_view.setReadOnly(True)
        self.ddl_view.setFont(theme.code_font(10))
        self.ddl_highlighter = theme.SqlHighlighter(self.ddl_view.document())

        self.table = QTableWidget()
        self.table.setAlternatingRowColors(True)
        self.table.setSortingEnabled(False)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.table.verticalHeader().setVisible(True)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self.show_table_context_menu)

        self.filter_edit = QLineEdit()
        self.filter_edit.setPlaceholderText("Optional WHERE clause, without the word WHERE. Example: amount > 100")
        self.limit_spin = QSpinBox()
        self.limit_spin.setRange(1, 100000)
        self.limit_spin.setValue(500)
        self.offset_spin = QSpinBox()
        self.offset_spin.setRange(0, 100000000)
        self.offset_spin.setValue(0)

        self.load_btn = QPushButton("Load / Refresh")
        self.load_btn.clicked.connect(self.load_current_table)
        self.prev_btn = QPushButton("Prev")
        self.prev_btn.clicked.connect(self.prev_page)
        self.next_btn = QPushButton("Next")
        self.next_btn.clicked.connect(self.next_page)
        self.save_table_btn = QPushButton("Apply Table Edits")
        self.save_table_btn.setObjectName("accent")
        self.save_table_btn.clicked.connect(self.apply_table_edits)
        self.add_row_btn = QPushButton("Add Row")
        self.add_row_btn.clicked.connect(self.add_blank_row)
        self.delete_rows_btn = QPushButton("Delete Selected Rows")
        self.delete_rows_btn.setObjectName("danger")
        self.delete_rows_btn.clicked.connect(self.delete_selected_rows)
        self.export_csv_btn = QPushButton("Export Displayed CSV")
        self.export_csv_btn.clicked.connect(self.export_displayed_csv)

        controls = QHBoxLayout()
        controls.addWidget(QLabel("Filter:"))
        controls.addWidget(self.filter_edit, 1)
        controls.addWidget(QLabel("Limit:"))
        controls.addWidget(self.limit_spin)
        controls.addWidget(QLabel("Offset:"))
        controls.addWidget(self.offset_spin)
        controls.addWidget(self.prev_btn)
        controls.addWidget(self.next_btn)
        controls.addWidget(self.load_btn)
        controls.addWidget(self.add_row_btn)
        controls.addWidget(self.delete_rows_btn)
        controls.addWidget(self.save_table_btn)
        controls.addWidget(self.export_csv_btn)

        data_tab = QWidget()
        data_layout = QVBoxLayout(data_tab)
        data_layout.addLayout(controls)
        data_layout.addWidget(self.table)

        self.sql_editor = QPlainTextEdit()
        self.sql_editor.setFont(theme.code_font(10))
        self.sql_editor.setPlaceholderText(
            "Write SQL here. Select SQL and press Ctrl+Enter to run selection, or run the whole editor."
        )
        self.sql_highlighter = theme.SqlHighlighter(self.sql_editor.document())

        self.sql_results = QTableWidget()
        self.sql_results.setAlternatingRowColors(True)
        self.sql_results.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)

        self.run_sql_btn = QPushButton("Run SQL")
        self.run_sql_btn.setObjectName("accent")
        self.run_sql_btn.clicked.connect(self.run_sql)
        self.run_selected_sql_btn = QPushButton("Run Selected")
        self.run_selected_sql_btn.clicked.connect(lambda: self.run_sql(selected_only=True))
        self.clear_results_btn = QPushButton("Clear Results")
        self.clear_results_btn.clicked.connect(lambda: self.sql_results.setRowCount(0))

        sql_controls = QHBoxLayout()
        sql_controls.addWidget(self.run_sql_btn)
        sql_controls.addWidget(self.run_selected_sql_btn)
        sql_controls.addWidget(self.clear_results_btn)
        sql_controls.addStretch(1)

        sql_tab = QWidget()
        sql_layout = QVBoxLayout(sql_tab)
        sql_layout.addLayout(sql_controls)
        sql_layout.addWidget(self.sql_editor, 2)
        sql_layout.addWidget(QLabel("Results / messages:"))
        sql_layout.addWidget(self.sql_results, 3)

        self.tabs = QTabWidget()
        self.tabs.addTab(data_tab, "Table Data")
        self.tabs.addTab(sql_tab, "SQL Editor")
        self.tabs.addTab(self.ddl_view, "Schema SQL / DDL")

        right_splitter = QSplitter(Qt.Orientation.Vertical)
        right_splitter.addWidget(self.tabs)
        right_splitter.setSizes([800])

        main_splitter = QSplitter(Qt.Orientation.Horizontal)
        main_splitter.addWidget(self.schema_tree)
        main_splitter.addWidget(right_splitter)
        main_splitter.setSizes([280, 1070])

        self.setCentralWidget(main_splitter)

    def _build_actions(self):
        toolbar = QToolBar("Main")
        self.addToolBar(toolbar)

        open_db = QAction("Open DB", self)
        open_db.setShortcut(QKeySequence.StandardKey.Open)
        open_db.triggered.connect(lambda: self.open_database_dialog(read_only=False))

        open_db_ro = QAction("Open DB Read-Only", self)
        open_db_ro.triggered.connect(lambda: self.open_database_dialog(read_only=True))

        close_db = QAction("Close DB", self)
        close_db.triggered.connect(self.close_database)

        backup_db = QAction("Backup DB", self)
        backup_db.triggered.connect(self.backup_database)

        open_sql = QAction("Open SQL File", self)
        open_sql.triggered.connect(self.open_sql_file)

        save_sql = QAction("Save SQL File", self)
        save_sql.setShortcut(QKeySequence.StandardKey.Save)
        save_sql.triggered.connect(self.save_sql_file)

        save_sql_as = QAction("Save SQL File As", self)
        save_sql_as.triggered.connect(self.save_sql_file_as)

        refresh_schema = QAction("Refresh Schema", self)
        refresh_schema.setShortcut(QKeySequence.StandardKey.Refresh)
        refresh_schema.triggered.connect(self.refresh_schema)

        commit = QAction("Commit", self)
        commit.triggered.connect(self.commit_changes)

        rollback = QAction("Rollback", self)
        rollback.triggered.connect(self.rollback_changes)

        run_sql = QAction("Run SQL", self)
        run_sql.setShortcut(QKeySequence("Ctrl+Enter"))
        run_sql.triggered.connect(self.run_sql)

        run_selected = QAction("Run Selected SQL", self)
        run_selected.setShortcut(QKeySequence("Ctrl+Shift+Enter"))
        run_selected.triggered.connect(lambda: self.run_sql(selected_only=True))

        file_menu = self.menuBar().addMenu("&File")
        for action in [open_db, open_db_ro, close_db, backup_db, open_sql, save_sql, save_sql_as]:
            file_menu.addAction(action)
        file_menu.addSeparator()
        file_menu.addAction("Exit", self.close)

        db_menu = self.menuBar().addMenu("&Database")
        for action in [refresh_schema, commit, rollback]:
            db_menu.addAction(action)

        table_menu = self.menuBar().addMenu("&Table")
        table_menu.addAction("Reload Current Table", self.load_current_table)
        table_menu.addAction("Apply Table Edits", self.apply_table_edits)
        table_menu.addAction("Add Row", self.add_blank_row)
        table_menu.addAction("Delete Selected Rows", self.delete_selected_rows)
        table_menu.addAction("Export Displayed CSV", self.export_displayed_csv)

        sql_menu = self.menuBar().addMenu("&SQL")
        sql_menu.addAction(run_sql)
        sql_menu.addAction(run_selected)

        for action in [open_db, open_db_ro, backup_db, refresh_schema, commit, rollback, run_sql]:
            toolbar.addAction(action)

    def _update_chips(self):
        if not hasattr(self, "mode_chip"):
            return
        if not self.conn:
            self.mode_chip.setText("NO DB")
            self.mode_chip.setProperty("mode", "off")
        elif self.read_only:
            self.mode_chip.setText("READ-ONLY")
            self.mode_chip.setProperty("mode", "ro")
        else:
            self.mode_chip.setText("READ/WRITE")
            self.mode_chip.setProperty("mode", "rw")

        self.pending_chip.setText("PENDING" if self.pending_changes else "CLEAN")
        self.pending_chip.setProperty("pending", "true" if self.pending_changes else "false")

        for chip in (self.mode_chip, self.pending_chip):
            chip.style().unpolish(chip)
            chip.style().polish(chip)

    def set_pending(self, pending: bool):
        self.pending_changes = pending
        self._update_chips()

    def _restore_settings(self):
        geometry = self.settings.value("geometry")
        if geometry:
            self.restoreGeometry(geometry)

    def closeEvent(self, event):
        if not self.confirm_pending_changes():
            event.ignore()
            return
        self.settings.setValue("geometry", self.saveGeometry())
        self.close_database(force=True)
        event.accept()

    def confirm_pending_changes(self) -> bool:
        if not self.conn or not self.pending_changes:
            return True

        choice = QMessageBox.question(
            self,
            "Pending database changes",
            "There are pending uncommitted database changes.\n\nCommit them before continuing?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if choice == QMessageBox.StandardButton.Cancel:
            return False
        if choice == QMessageBox.StandardButton.Yes:
            self.commit_changes()
        elif choice == QMessageBox.StandardButton.No:
            self.rollback_changes()
        return True

    def open_database_dialog(self, read_only: bool = False):
        last_dir = self.settings.value("last_db_dir", str(Path.home()))
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Open SQLite database",
            last_dir,
            "SQLite DB (*.db *.sqlite *.sqlite3);;All files (*.*)",
        )
        if not path:
            return
        self.settings.setValue("last_db_dir", str(Path(path).parent))
        self.open_database(path, read_only=read_only)

    def open_database(self, path: str, read_only: bool = False):
        if not self.confirm_pending_changes():
            return
        self.close_database(force=True)

        try:
            if read_only:
                self.conn = sqlite3.connect(sqlite_uri_readonly(path), uri=True)
            else:
                self.conn = sqlite3.connect(path)
            self.conn.row_factory = sqlite3.Row
            self.conn.execute("PRAGMA foreign_keys = ON")
            self.db_path = path
            self.read_only = read_only
            self.set_pending(False)
            self.refresh_schema()
            mode = "READ-ONLY" if read_only else "READ/WRITE"
            self.status.showMessage(f"Opened {path} ({mode})")
            self.setWindowTitle(f"{APP_NAME} - {Path(path).name} [{mode}]")
        except Exception as exc:
            QMessageBox.critical(self, "Open database failed", f"{exc}\n\n{traceback.format_exc()}")

    def close_database(self, force: bool = False):
        if not force and not self.confirm_pending_changes():
            return

        if self.conn:
            try:
                self.conn.close()
            except Exception:
                pass

        self.conn = None
        self.db_path = None
        self.read_only = False
        self.set_pending(False)
        self.current_object_name = None
        self.current_object_type = None
        self.schema_tree.clear()
        self.table.clear()
        self.table.setRowCount(0)
        self.table.setColumnCount(0)
        self.ddl_view.clear()
        self.setWindowTitle(APP_NAME)
        self.status.showMessage("Database closed")

    def backup_database(self):
        if not self.conn or not self.db_path:
            QMessageBox.information(self, "No database", "Open a database first.")
            return

        src = Path(self.db_path)
        suggested = src.with_name(f"{src.stem}.backup_{datetime.now():%Y%m%d_%H%M%S}{src.suffix}")
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save database backup",
            str(suggested),
            "SQLite DB (*.db *.sqlite *.sqlite3);;All files (*.*)",
        )
        if not path:
            return

        try:
            dest = sqlite3.connect(path)
            with dest:
                self.conn.backup(dest)
            dest.close()
            self.status.showMessage(f"Backup written: {path}")
        except Exception as exc:
            QMessageBox.critical(self, "Backup failed", f"{exc}\n\n{traceback.format_exc()}")

    def refresh_schema(self):
        if not self.conn:
            return

        self.schema_tree.clear()
        root = QTreeWidgetItem([Path(self.db_path).name if self.db_path else "Database"])
        self.schema_tree.addTopLevelItem(root)

        groups = {
            "table": QTreeWidgetItem(["Tables"]),
            "view": QTreeWidgetItem(["Views"]),
            "index": QTreeWidgetItem(["Indexes"]),
            "trigger": QTreeWidgetItem(["Triggers"]),
        }
        for g in groups.values():
            root.addChild(g)

        rows = self.conn.execute(
            """
            SELECT name, type, sql
            FROM sqlite_master
            WHERE type IN ('table', 'view', 'index', 'trigger')
              AND name NOT LIKE 'sqlite_%'
            ORDER BY type, name
            """
        ).fetchall()

        for row in rows:
            item = QTreeWidgetItem([row["name"]])
            item.setData(0, Qt.ItemDataRole.UserRole, {"name": row["name"], "type": row["type"], "sql": row["sql"]})
            groups[row["type"]].addChild(item)

        self.schema_tree.expandAll()
        self.status.showMessage("Schema refreshed")

    def on_schema_selection_changed(self):
        items = self.schema_tree.selectedItems()
        if not items:
            return
        data = items[0].data(0, Qt.ItemDataRole.UserRole)
        if not data:
            return

        self.current_object_name = data["name"]
        self.current_object_type = data["type"]
        self.ddl_view.setPlainText(data.get("sql") or "")

        if self.current_object_type in {"table", "view"}:
            self.tabs.setCurrentIndex(0)
            self.offset_spin.setValue(0)
            self.load_current_table()
        else:
            self.tabs.setCurrentIndex(2)

    def load_current_table(self):
        if not self.conn or not self.current_object_name:
            return
        if self.current_object_type not in {"table", "view"}:
            return

        table_name = self.current_object_name
        quoted_table = quote_ident(table_name)
        self.loading_table = True
        self.table.setSortingEnabled(False)
        self.table.clear()
        self.table.setRowCount(0)
        self.original_rows = []
        self.new_row_numbers = set()
        self.current_columns = []
        self.current_column_types = {}
        self.current_pk_cols = []
        self.current_key_mode = None

        try:
            info = self.conn.execute(f"PRAGMA table_info({quoted_table})").fetchall()
            self.current_columns = [r["name"] for r in info]
            self.current_column_types = {r["name"]: (r["type"] or "") for r in info}
            self.current_pk_cols = [r["name"] for r in sorted(info, key=lambda r: r["pk"]) if r["pk"]]

            if not self.current_columns:
                raise RuntimeError("No columns found. This object may not be queryable.")

            select_cols = ", ".join(quote_ident(c) for c in self.current_columns)
            where = self.filter_edit.text().strip()
            where_sql = ""
            if where:
                if ";" in where:
                    raise ValueError("Filter must be a WHERE expression only; semicolons are not allowed here.")
                where_sql = f" WHERE {where}"

            limit = int(self.limit_spin.value())
            offset = int(self.offset_spin.value())

            base_sql = f"SELECT {select_cols} FROM {quoted_table}{where_sql} LIMIT ? OFFSET ?"
            rowid_sql = f"SELECT rowid AS __rowid__, {select_cols} FROM {quoted_table}{where_sql} LIMIT ? OFFSET ?"

            rows = []
            if self.current_object_type == "table" and not self.current_pk_cols:
                try:
                    rows = self.conn.execute(rowid_sql, (limit, offset)).fetchall()
                    self.current_key_mode = "rowid"
                except sqlite3.DatabaseError:
                    rows = self.conn.execute(base_sql, (limit, offset)).fetchall()
                    self.current_key_mode = None
            else:
                rows = self.conn.execute(base_sql, (limit, offset)).fetchall()
                self.current_key_mode = "pk" if self.current_pk_cols else None

            self.table.setColumnCount(len(self.current_columns))
            self.table.setHorizontalHeaderLabels(self.current_columns)
            self.table.setRowCount(len(rows))

            editable = (self.current_object_type == "table") and (not self.read_only) and (self.current_key_mode is not None)

            for r_idx, row in enumerate(rows):
                original = {}
                if self.current_key_mode == "rowid":
                    original["__rowid__"] = row["__rowid__"]

                for c_idx, col in enumerate(self.current_columns):
                    value = row[col]
                    original[col] = value
                    item = QTableWidgetItem(display_value(value))
                    item.setData(Qt.ItemDataRole.UserRole, value)

                    flags = item.flags()
                    if not editable or isinstance(value, bytes):
                        flags &= ~Qt.ItemFlag.ItemIsEditable
                    item.setFlags(flags)
                    self.table.setItem(r_idx, c_idx, item)

                self.original_rows.append(original)

            self.table.resizeColumnsToContents()
            if not editable:
                reason = "read-only database/view/no primary key or rowid"
                self.status.showMessage(f"Loaded {len(rows)} rows from {table_name}; editing disabled ({reason}).")
            else:
                self.status.showMessage(f"Loaded {len(rows)} rows from {table_name}. Edit cells, then Apply Table Edits.")
        except Exception as exc:
            QMessageBox.critical(self, "Load table failed", f"{exc}\n\n{traceback.format_exc()}")
        finally:
            self.loading_table = False

    def parse_cell_value(self, text: str, original, declared_type: str):
        if text == NULL_TOKEN:
            return None
        if isinstance(original, bytes):
            return original

        dtype = (declared_type or "").upper()

        if text == "":
            return ""

        try:
            if "INT" in dtype:
                return int(text)
            if any(t in dtype for t in ["REAL", "FLOA", "DOUB"]):
                return float(text)
            if any(t in dtype for t in ["NUM", "DEC", "BOOL"]):
                if re.fullmatch(r"[-+]?\d+", text):
                    return int(text)
                if re.fullmatch(r"[-+]?\d*\.\d+", text):
                    return float(text)
        except ValueError:
            return text

        if isinstance(original, int):
            try:
                return int(text)
            except ValueError:
                return text
        if isinstance(original, float):
            try:
                return float(text)
            except ValueError:
                return text

        return text

    def current_row_values(self, row_num: int) -> dict:
        values = {}
        original = self.original_rows[row_num] if row_num < len(self.original_rows) else {}
        for c_idx, col in enumerate(self.current_columns):
            item = self.table.item(row_num, c_idx)
            text = item.text() if item else NULL_TOKEN
            values[col] = self.parse_cell_value(text, original.get(col), self.current_column_types.get(col, ""))
        return values

    def key_where_clause_and_values(self, original: dict):
        if self.current_key_mode == "pk":
            where = " AND ".join(
                f"{quote_ident(col)} IS ?" if original.get(col) is None else f"{quote_ident(col)} = ?"
                for col in self.current_pk_cols
            )
            values = [original.get(col) for col in self.current_pk_cols]
            return where, values
        if self.current_key_mode == "rowid":
            return "rowid = ?", [original["__rowid__"]]
        raise RuntimeError("This table cannot be safely edited because no primary key or rowid is available.")

    def add_blank_row(self):
        if not self.conn or not self.current_object_name:
            QMessageBox.information(self, "No table", "Open a table first.")
            return
        if self.read_only or self.current_object_type != "table":
            QMessageBox.warning(self, "Read-only", "Rows can only be added to read/write tables.")
            return

        row = self.table.rowCount()
        self.table.insertRow(row)
        self.new_row_numbers.add(row)

        for c_idx, col in enumerate(self.current_columns):
            item = QTableWidgetItem(NULL_TOKEN)
            self.table.setItem(row, c_idx, item)

        self.status.showMessage("Blank row added. Fill values, then Apply Table Edits.")

    def apply_table_edits(self):
        if not self.conn or not self.current_object_name:
            return
        if self.read_only:
            QMessageBox.warning(self, "Read-only", "This database was opened read-only.")
            return
        if self.current_object_type != "table":
            QMessageBox.warning(self, "Not editable", "Only tables can be edited directly.")
            return
        if self.current_key_mode is None and not self.new_row_numbers:
            QMessageBox.warning(self, "Not editable", "This table has no primary key or rowid, so existing rows cannot be safely edited.")
            return

        try:
            table_name = quote_ident(self.current_object_name)
            updates = 0
            inserts = 0

            for row_num in range(self.table.rowCount()):
                values = self.current_row_values(row_num)

                if row_num in self.new_row_numbers:
                    cols = list(values.keys())
                    placeholders = ", ".join(["?"] * len(cols))
                    col_sql = ", ".join(quote_ident(c) for c in cols)
                    self.conn.execute(
                        f"INSERT INTO {table_name} ({col_sql}) VALUES ({placeholders})",
                        [values[c] for c in cols],
                    )
                    inserts += 1
                    continue

                if row_num >= len(self.original_rows):
                    continue

                original = self.original_rows[row_num]
                changes = {}
                for col in self.current_columns:
                    if values[col] != original.get(col):
                        changes[col] = values[col]

                if not changes:
                    continue

                set_sql = ", ".join(f"{quote_ident(c)} = ?" for c in changes.keys())
                where_sql, where_values = self.key_where_clause_and_values(original)
                params = list(changes.values()) + where_values
                self.conn.execute(f"UPDATE {table_name} SET {set_sql} WHERE {where_sql}", params)
                updates += 1

            if inserts or updates:
                self.set_pending(True)
                self.status.showMessage(f"Applied {updates} updates and {inserts} inserts. Click Commit to persist, or Rollback to discard.")
                self.refresh_schema()
                self.load_current_table()
            else:
                self.status.showMessage("No table changes detected.")
        except Exception as exc:
            QMessageBox.critical(self, "Apply edits failed", f"{exc}\n\n{traceback.format_exc()}")

    def delete_selected_rows(self):
        if not self.conn or not self.current_object_name:
            return
        if self.read_only:
            QMessageBox.warning(self, "Read-only", "This database was opened read-only.")
            return
        if self.current_object_type != "table":
            QMessageBox.warning(self, "Not editable", "Only tables can be edited directly.")
            return

        selected_rows = sorted({idx.row() for idx in self.table.selectedIndexes()}, reverse=True)
        if not selected_rows:
            QMessageBox.information(self, "No rows selected", "Select one or more rows first.")
            return

        choice = QMessageBox.question(
            self,
            "Delete rows",
            f"Delete {len(selected_rows)} selected row(s)?\n\nThis is applied to the current transaction. You can still Rollback before Commit.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if choice != QMessageBox.StandardButton.Yes:
            return

        try:
            table_name = quote_ident(self.current_object_name)
            deleted = 0

            for row_num in selected_rows:
                if row_num in self.new_row_numbers:
                    self.table.removeRow(row_num)
                    self.new_row_numbers.discard(row_num)
                    continue
                if row_num >= len(self.original_rows):
                    continue

                original = self.original_rows[row_num]
                where_sql, where_values = self.key_where_clause_and_values(original)
                self.conn.execute(f"DELETE FROM {table_name} WHERE {where_sql}", where_values)
                deleted += 1

            if deleted:
                self.set_pending(True)
                self.status.showMessage(f"Deleted {deleted} row(s). Click Commit to persist, or Rollback to discard.")
                self.load_current_table()
        except Exception as exc:
            QMessageBox.critical(self, "Delete failed", f"{exc}\n\n{traceback.format_exc()}")

    def show_table_context_menu(self, pos: QPoint):
        menu = QMenu(self)
        copy_action = menu.addAction("Copy selected cells")
        null_action = menu.addAction("Set selected cells to <NULL>")
        action = menu.exec(self.table.mapToGlobal(pos))

        if action == copy_action:
            self.copy_selected_cells()
        elif action == null_action:
            for idx in self.table.selectedIndexes():
                item = self.table.item(idx.row(), idx.column())
                if item and (item.flags() & Qt.ItemFlag.ItemIsEditable):
                    item.setText(NULL_TOKEN)

    def copy_selected_cells(self):
        indexes = self.table.selectedIndexes()
        if not indexes:
            return

        rows = sorted(set(i.row() for i in indexes))
        cols = sorted(set(i.column() for i in indexes))
        grid = []
        for r in rows:
            line = []
            for c in cols:
                item = self.table.item(r, c)
                line.append(item.text() if item else "")
            grid.append("\t".join(line))
        QApplication.clipboard().setText("\n".join(grid))
        self.status.showMessage("Copied selected cells.")

    def export_displayed_csv(self):
        if self.table.rowCount() == 0:
            QMessageBox.information(self, "No data", "There is no displayed table data to export.")
            return

        path, _ = QFileDialog.getSaveFileName(self, "Export displayed rows to CSV", str(Path.home() / "table_export.csv"), "CSV (*.csv)")
        if not path:
            return

        try:
            with open(path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(self.current_columns)
                for r in range(self.table.rowCount()):
                    writer.writerow([
                        self.table.item(r, c).text() if self.table.item(r, c) else ""
                        for c in range(self.table.columnCount())
                    ])
            self.status.showMessage(f"CSV exported: {path}")
        except Exception as exc:
            QMessageBox.critical(self, "Export failed", f"{exc}\n\n{traceback.format_exc()}")

    def prev_page(self):
        new_offset = max(0, self.offset_spin.value() - self.limit_spin.value())
        self.offset_spin.setValue(new_offset)
        self.load_current_table()

    def next_page(self):
        self.offset_spin.setValue(self.offset_spin.value() + self.limit_spin.value())
        self.load_current_table()

    def open_sql_file(self):
        last_dir = self.settings.value("last_sql_dir", str(Path.home()))
        path, _ = QFileDialog.getOpenFileName(self, "Open SQL file", last_dir, "SQL files (*.sql);;All files (*.*)")
        if not path:
            return

        try:
            text = Path(path).read_text(encoding="utf-8")
        except UnicodeDecodeError:
            text = Path(path).read_text(encoding="utf-8-sig")

        self.current_sql_file = path
        self.settings.setValue("last_sql_dir", str(Path(path).parent))
        self.sql_editor.setPlainText(text)
        self.tabs.setCurrentIndex(1)
        self.status.showMessage(f"Opened SQL file: {path}")

    def save_sql_file(self):
        if not self.current_sql_file:
            self.save_sql_file_as()
            return
        try:
            Path(self.current_sql_file).write_text(self.sql_editor.toPlainText(), encoding="utf-8")
            self.status.showMessage(f"Saved SQL file: {self.current_sql_file}")
        except Exception as exc:
            QMessageBox.critical(self, "Save SQL failed", f"{exc}\n\n{traceback.format_exc()}")

    def save_sql_file_as(self):
        path, _ = QFileDialog.getSaveFileName(self, "Save SQL file", str(Path.home() / "script.sql"), "SQL files (*.sql);;All files (*.*)")
        if not path:
            return
        self.current_sql_file = path
        self.save_sql_file()

    def selected_or_all_sql(self, selected_only: bool = False) -> str:
        cursor = self.sql_editor.textCursor()
        selected = cursor.selectedText().replace("\u2029", "\n")
        if selected_only and selected.strip():
            return selected
        if selected.strip():
            return selected
        return self.sql_editor.toPlainText()

    def run_sql(self, checked=False, selected_only: bool = False):
        if not self.conn:
            QMessageBox.information(self, "No database", "Open a database first.")
            return

        sql = self.selected_or_all_sql(selected_only=selected_only).strip()
        if not sql:
            return

        if self.read_only and is_probably_write(sql):
            QMessageBox.warning(self, "Read-only", "This database was opened read-only, so write SQL is blocked.")
            return

        try:
            if is_probably_query(sql):
                cur = self.conn.execute(sql)
                if cur.description:
                    rows = cur.fetchmany(10000)
                    headers = [d[0] for d in cur.description]
                    self.populate_sql_results(headers, rows)
                    self.status.showMessage(f"Query returned {len(rows)} row(s).")
                else:
                    self.populate_message_result("Statement executed; no result set.")
                    self.status.showMessage("Statement executed.")
            else:
                self.conn.executescript(sql)
                self.set_pending(True)
                self.populate_message_result("SQL script executed. Click Commit to persist, or Rollback to discard.")
                self.refresh_schema()
                if self.current_object_name and self.current_object_type in {"table", "view"}:
                    self.load_current_table()
                self.status.showMessage("SQL script executed; pending transaction.")
        except Exception as exc:
            self.populate_message_result(f"ERROR:\n{exc}")
            QMessageBox.critical(self, "SQL execution failed", f"{exc}\n\n{traceback.format_exc()}")

    def populate_sql_results(self, headers: list[str], rows: list[sqlite3.Row]):
        self.sql_results.clear()
        self.sql_results.setColumnCount(len(headers))
        self.sql_results.setHorizontalHeaderLabels(headers)
        self.sql_results.setRowCount(len(rows))

        for r_idx, row in enumerate(rows):
            for c_idx, header in enumerate(headers):
                item = QTableWidgetItem(display_value(row[header]))
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.sql_results.setItem(r_idx, c_idx, item)

        self.sql_results.resizeColumnsToContents()

    def populate_message_result(self, message: str):
        self.sql_results.clear()
        self.sql_results.setColumnCount(1)
        self.sql_results.setHorizontalHeaderLabels(["Message"])
        self.sql_results.setRowCount(1)
        item = QTableWidgetItem(message)
        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        self.sql_results.setItem(0, 0, item)
        self.sql_results.resizeColumnsToContents()

    def commit_changes(self):
        if not self.conn:
            return
        try:
            self.conn.commit()
            self.set_pending(False)
            self.status.showMessage("Database changes committed.")
            self.refresh_schema()
            if self.current_object_name and self.current_object_type in {"table", "view"}:
                self.load_current_table()
        except Exception as exc:
            QMessageBox.critical(self, "Commit failed", f"{exc}\n\n{traceback.format_exc()}")

    def rollback_changes(self):
        if not self.conn:
            return
        try:
            self.conn.rollback()
            self.set_pending(False)
            self.status.showMessage("Database changes rolled back.")
            self.refresh_schema()
            if self.current_object_name and self.current_object_type in {"table", "view"}:
                self.load_current_table()
        except Exception as exc:
            QMessageBox.critical(self, "Rollback failed", f"{exc}\n\n{traceback.format_exc()}")


def main():
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName(ORG_NAME)
    theme.apply(app)
    win = SqliteWorkbench()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
