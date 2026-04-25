#!/opt/miniconda3/envs/zotero-obsidian/bin/python
"""Sync Zotero items to an Obsidian vault by reading from the local SQLite database."""

import argparse
import html
import re
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

# ── Configuration ──────────────────────────────────────────────────────────────
ZOTERO_DB      = Path("~/Zotero/zotero.sqlite").expanduser()
#OBSIDIAN_VAULT = Path("~/path/to/your/vault").expanduser()
OBSIDIAN_VAULT = "."
LITERATURE_DIR = "Literature"
READING_DIR    = "Notes"
FILENAME_FORMAT = "{year} {author} - {title}"

# ── Constants ──────────────────────────────────────────────────────────────────
IMPORT_TYPES = frozenset({
    "journalArticle", "conferencePaper", "preprint",
    "book", "bookSection", "report",
})

COLOR_EMOJI = {
    "#ffd400": "🟡",  # yellow
    "#facd5a": "🟡",  # light yellow
    "#f19837": "🟡",  # orange (no orange block emoji)
    "#ff6666": "🔴",  # red
    "#5fb236": "🟢",  # green
    "#2ea8e5": "🔵",  # blue
    "#a28ae5": "🟣",  # purple
    "#e56eee": "🟣",  # magenta -> purple (closest)
    "#aaaaaa": "⬜",  # gray
}

ANNOTATION_TYPE_NAME = {1: "highlight", 2: "note", 3: "underline", 4: "image", 5: "ink"}

_ILLEGAL_CHARS = re.compile(r'[/\\:*?"<>|\x00-\x1f]')


# ── ZoteroReader ───────────────────────────────────────────────────────────────

class ZoteroReader:
    """Read-only access to the Zotero SQLite database."""

    def __init__(self, db_path: Path) -> None:
        # immutable=1 skips lock acquisition so the script works while Zotero is open.
        # Zotero uses delete-journal mode (not WAL), so mode=ro alone cannot bypass
        # an exclusive lock held by the running app.
        uri = f"file:{db_path}?mode=ro&immutable=1"
        self.conn = sqlite3.connect(uri, uri=True)
        self.conn.row_factory = sqlite3.Row

    def close(self) -> None:
        self.conn.close()

    def get_qualifying_items(self, key: str | None = None) -> list[dict]:
        placeholders = ",".join("?" * len(IMPORT_TYPES))
        params: list = list(IMPORT_TYPES)
        extra = ""
        if key:
            extra = " AND i.key = ?"
            params.append(key)
        rows = self.conn.execute(f"""
            SELECT i.itemID, i.key, it.typeName
            FROM items i
            JOIN itemTypes it ON i.itemTypeID = it.itemTypeID
            WHERE it.typeName IN ({placeholders}){extra}
            ORDER BY i.itemID
        """, params).fetchall()
        return [dict(r) for r in rows]

    def _get_fields(self, item_id: int) -> dict:
        rows = self.conn.execute("""
            SELECT f.fieldName, idv.value
            FROM itemData id
            JOIN fieldsCombined f ON id.fieldID = f.fieldID
            JOIN itemDataValues idv ON id.valueID = idv.valueID
            WHERE id.itemID = ?
        """, (item_id,)).fetchall()
        return {r[0]: r[1] for r in rows}

    def _get_authors(self, item_id: int) -> list[dict]:
        rows = self.conn.execute("""
            SELECT c.firstName, c.lastName, ct.creatorType, ic.orderIndex
            FROM itemCreators ic
            JOIN creators c ON ic.creatorID = c.creatorID
            JOIN creatorTypes ct ON ic.creatorTypeID = ct.creatorTypeID
            WHERE ic.itemID = ?
            ORDER BY ic.orderIndex
        """, (item_id,)).fetchall()
        return [dict(r) for r in rows]

    def _get_annotations(self, item_id: int) -> list[dict]:
        # Annotations live on PDF attachments; traverse attachment -> paper chain.
        rows = self.conn.execute("""
            SELECT ia.type, ia.text, ia.comment, ia.color, ia.pageLabel
            FROM itemAnnotations ia
            JOIN itemAttachments att ON ia.parentItemID = att.itemID
            WHERE att.parentItemID = ?
            ORDER BY ia.sortIndex
        """, (item_id,)).fetchall()
        return [dict(r) for r in rows]

    def _get_notes(self, item_id: int) -> list[str]:
        rows = self.conn.execute(
            "SELECT note FROM itemNotes WHERE parentItemID = ?", (item_id,)
        ).fetchall()
        return [r[0] for r in rows if r[0]]

    def build_item(self, item_id: int, key: str, type_name: str) -> dict:
        fields = self._get_fields(item_id)
        date_str = fields.get("date", "")
        m = re.search(r"\b(\d{4})\b", date_str)
        year = m.group(1) if m else ""
        return {
            "itemID":      item_id,
            "key":         key,
            "typeName":    type_name,
            "title":       fields.get("title", ""),
            "abstract":    fields.get("abstractNote", ""),
            "doi":         fields.get("DOI", ""),
            "url":         fields.get("url", ""),
            "journal":     fields.get("publicationTitle", ""),
            "year":        year,
            "volume":      fields.get("volume", ""),
            "issue":       fields.get("issue", ""),
            "pages":       fields.get("pages", ""),
            "authors":     self._get_authors(item_id),
            "annotations": self._get_annotations(item_id),
            "notes":       self._get_notes(item_id),
        }


# ── NoteBuilder ────────────────────────────────────────────────────────────────

class NoteBuilder:
    """Render Markdown import and reading notes from a Zotero item dict."""

    def _author_names(self, authors: list[dict]) -> list[str]:
        out = []
        for a in authors:
            first, last = (a.get("firstName") or "").strip(), (a.get("lastName") or "").strip()
            if first and last:
                out.append(f"{first} {last}")
            elif last:
                out.append(last)
            elif first:
                out.append(first)
        return out

    def _strip_html(self, text: str) -> str:
        text = html.unescape(text)
        text = re.sub(r"<[^>]+>", "", text)
        return re.sub(r"\s+", " ", text).strip()

    def _annotation_emoji(self, color: str | None) -> str:
        return COLOR_EMOJI.get((color or "").lower(), "⬜")

    def _format_annotation(self, ann: dict) -> str:
        text    = (ann.get("text") or "").strip()
        comment = (ann.get("comment") or "").strip()
        if not text and not comment:
            return ""
        emoji    = self._annotation_emoji(ann.get("color"))
        page     = ann.get("pageLabel") or ""
        page_str = f" (p. {page})" if page else ""
        lines = []
        if text:
            lines.append(f"> {emoji} {text}{page_str}")
        if comment:
            lines.append(f"> *{comment}*")
        return "\n".join(lines)

    def _dump_frontmatter(self, data: dict) -> str:
        clean = {k: v for k, v in data.items() if v is not None and v != ""}
        return yaml.dump(clean, allow_unicode=True, default_flow_style=False, sort_keys=False)

    def import_note(self, item: dict) -> str:
        author_names = self._author_names(item["authors"])
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        fm: dict = {"zotero_key": item["key"]}
        if item["title"]:      fm["title"]   = item["title"]
        if author_names:       fm["authors"] = author_names
        if item["year"]:       fm["year"]    = item["year"]
        if item["journal"]:    fm["journal"] = item["journal"]
        if item["doi"]:        fm["doi"]     = item["doi"]
        fm["tags"]          = ["literature"]
        fm["last_imported"] = now

        lines = ["---", self._dump_frontmatter(fm).rstrip(), "---", ""]

        lines += ["## Abstract", ""]
        if item["abstract"]:
            lines.append(item["abstract"])
        lines.append("")

        lines += ["## Annotations", ""]
        ann_blocks = [self._format_annotation(a) for a in item["annotations"]]
        ann_blocks = [b for b in ann_blocks if b]
        if ann_blocks:
            lines.append("\n\n".join(ann_blocks))
        lines.append("")

        lines += ["## Notes", ""]
        for note_html in item["notes"]:
            plain = self._strip_html(note_html)
            if plain:
                lines += [plain, ""]

        return "\n".join(lines)

    def reading_note(self, item: dict) -> str:
        author_names = self._author_names(item["authors"])

        fm: dict = {"zotero_key": item["key"]}
        if item["title"]:  fm["title"]   = item["title"]
        if author_names:   fm["people"] = author_names
        if item["year"]:   fm["year"]    = item["year"]
        fm["tags"]   = ["reading-note"]
        fm["status"] = "unread"

        lines = ["---", self._dump_frontmatter(fm).rstrip(), "---", ""]
        lines += [
            "## Summary", "",
            "## Key Takeaways", "",
            "## Questions & Criticisms", "",
            "## Connection to My Work", "",
        ]
        return "\n".join(lines)


# ── ObsidianWriter ─────────────────────────────────────────────────────────────

class ObsidianWriter:
    """Handle all Obsidian vault file I/O."""

    def __init__(self, vault: Path, lit_dir: str, reading_dir: str) -> None:
        self.lit_path     = vault / lit_dir
        self.reading_path = vault / reading_dir
        self._key_cache: dict[str, Path] | None = None

    def _build_key_cache(self) -> dict[str, Path]:
        cache: dict[str, Path] = {}
        if not self.reading_path.exists():
            return cache
        for md_file in self.reading_path.rglob("*.md"):
            try:
                fm = _parse_frontmatter(md_file.read_text(encoding="utf-8"))
                key = fm.get("zotero_key")
                if key:
                    cache[str(key)] = md_file
            except Exception:
                pass
        return cache

    def _cache(self) -> dict[str, Path]:
        if self._key_cache is None:
            self._key_cache = self._build_key_cache()
        return self._key_cache

    def reading_note_exists(self, key: str) -> bool:
        return key in self._cache()

    def write_import_note(self, path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def write_reading_note(self, path: Path, content: str, key: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        self._cache()[key] = path

    def import_path(self, filename: str) -> Path:
        return self.lit_path / f"{filename}.md"

    def reading_path_for(self, filename: str) -> Path:
        return self.reading_path / f"{filename}.md"


# ── Helpers ────────────────────────────────────────────────────────────────────

def _parse_frontmatter(content: str) -> dict:
    """Extract and parse YAML frontmatter from the block between the first two --- delimiters."""
    parts = content.split("---", 2)
    if len(parts) < 3:
        return {}
    try:
        result = yaml.safe_load(parts[1])
        return result if isinstance(result, dict) else {}
    except yaml.YAMLError:
        return {}


def make_filename(item: dict, fmt: str = FILENAME_FORMAT, max_len: int = 80) -> str:
    authors = item["authors"]
    first_author = "Unknown"
    for a in authors:
        last = (a.get("lastName") or "").strip()
        first = (a.get("firstName") or "").strip()
        if last:
            first_author = last
            break
        if first:
            first_author = first
            break

    title = item["title"] or "Untitled"
    year  = item["year"] or "n.d."

    name = fmt.format(author=first_author, year=year, title=title)
    if len(name) > max_len:
        name = name[:max_len].rstrip()
    name = _ILLEGAL_CHARS.sub("_", name).strip("_ ")
    return name or item["key"]


# ── main ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Sync Zotero items to an Obsidian vault."
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Print what would be written without touching any files.",
    )
    parser.add_argument(
        "--key", metavar="KEY",
        help="Process only the Zotero item with this key (useful for testing).",
    )
    args = parser.parse_args()

    reader  = ZoteroReader(ZOTERO_DB)
    builder = NoteBuilder()
    writer  = ObsidianWriter(OBSIDIAN_VAULT, LITERATURE_DIR, READING_DIR)

    items_meta = reader.get_qualifying_items(key=args.key)
    if args.key and not items_meta:
        print(f"No qualifying item found with key: {args.key}", file=sys.stderr)
        sys.exit(1)

    import_written   = 0
    reading_created  = 0
    reading_skipped  = 0

    for meta in items_meta:
        item     = reader.build_item(meta["itemID"], meta["key"], meta["typeName"])
        filename = make_filename(item)

        imp_path  = writer.import_path(filename)
        read_path = writer.reading_path_for(filename)
        read_exists = writer.reading_note_exists(item["key"])

        if args.dry_run:
            print(f"[{item['key']}] {filename!r}")
            print(f"  Import note:  {imp_path}  → WRITE")
            if read_exists:
                print(f"  Reading note: SKIP (zotero_key already present in vault)")
            else:
                print(f"  Reading note: {read_path}  → CREATE")
        else:
            writer.write_import_note(imp_path, builder.import_note(item))
            import_written += 1

            if read_exists:
                reading_skipped += 1
            else:
                writer.write_reading_note(read_path, builder.reading_note(item), item["key"])
                reading_created += 1

    reader.close()

    if args.dry_run:
        total = len(items_meta)
        would_skip = sum(1 for m in items_meta if writer.reading_note_exists(m["key"]))
        print(f"\n--- Dry run summary ---")
        print(f"Items found:           {total}")
        print(f"Import notes:          {total} (all would be written)")
        print(f"Reading notes created: {total - would_skip}")
        print(f"Reading notes skipped: {would_skip}")
    else:
        print(f"Import notes written:  {import_written}")
        print(f"Reading notes created: {reading_created}")
        print(f"Reading notes skipped: {reading_skipped}")


if __name__ == "__main__":
    main()
