# Zotero to Obsidian Bulk Importer

A script that syncs your Zotero library into an Obsidian vault by reading directly from Zotero's local SQLite database.

For each qualifying item (journal articles, conference papers, preprints, books, book sections, and reports), the script creates two notes:

- An **import note** in a [Zotero folder](./Zotero/) containing YAML frontmatter, the abstract, inline annotations extracted from PDFs, and any standalone Zotero notes. These notes are fully managed by the script and overwritten on each run.
- A **reading note** in a [Papers folder](./Papers/) containing frontmatter and empty section headers for your own writing. This is created once and never overwritten.

Settings can be configured in [config.yaml](./config.yaml) and I use [Papers.base](./Papers.base) to keep track of papers within Obsidian.

## Installation

### Download

This repository can be downloaded through GitHub by either using the website or terminal. To download on the website, navigate to the top of this page, click the green `Clone or download` button, and select `Download ZIP` to download this repository in a compressed format. To install using GitHub on terminal, type:

```bash
git clone https://github.com/breardon/zotero-to-obsidian-bulk-importer.git
cd zotero-to-obsidian-bulk-importer
```

### Python dependencies

This repository uses Python 3.13. We recommend using a [virtual environment](https://docs.python.org/3/tutorial/venv.html) and running Python with either [Anaconda](https://www.anaconda.com/download/) or [Miniconda](https://conda.io/miniconda.html).

Run the following from this repository's directory to create a virtual environment and install dependencies with Anaconda or Miniconda:

```bash
conda env create -f environment.yml
conda activate zotero-obsidian
```

## Configuration

All configuration lives in [config.yaml](config.yaml). Edit the `settings` block before running the script:

```yaml
settings:
  zotero_db: ~/Zotero/zotero.sqlite
  obsidian_vault: ~/path/to/your/vault
  literature_dir: Literature
  reading_dir: Notes
  color_emojis: true
```

| Key | Description |
|---|---|
| `zotero_db` | Path to your Zotero SQLite database |
| `obsidian_vault` | Path to your Obsidian vault root |
| `literature_dir` | Subfolder name for import (highlights) notes |
| `reading_dir` | Subfolder name for reading notes |
| `color_emojis` | If `true`, annotation highlights are prefixed with a color emoji corresponding to the highlight color within Zotero (🟡 🔴 🟢 🔵 🟣) |

## Usage

Run a dry run first to preview what would be written without touching any files:

```bash
python zotero_to_obsidian.py --dry-run
```

To process a single item by its Zotero key (useful for testing):

```bash
python zotero_to_obsidian.py --dry-run --key ABC123XY
python zotero_to_obsidian.py --key ABC123XY
```

To sync your full Zotero library:

```bash
python zotero_to_obsidian.py
```

The script is safe to run repeatedly. Import notes are always overwritten with fresh data from Zotero. Reading notes are only created if no existing file in `reading_dir` already has a matching `zotero_key` in its frontmatter, so any notes you have written will never be touched.

The script can be run while Zotero is open.

## Customization

### Filenames

Both note types are named after the Zotero item key. An optional suffix can be appended per note type in `config.yaml`:

```yaml
import_note:
  filename_suffix: "-Zotero"   # produces GHWZTAGC-Zotero.md

reading_note:
  filename_suffix: ""          # produces GHWZTAGC.md
```

### Frontmatter fields

The `frontmatter` block under each note type in `config.yaml` controls which fields appear in the output and in what order. Add, remove, or reorder lines freely.

```yaml
import_note:
  frontmatter:
    categories: ["[[Zotero Highlights]]"]
    date: today
    doi: doi
    journal: journal_wikilink
    people: authors_wikilink
    ...
```

Each value is a **value expression** resolved at render time:

| Expression | Output |
| --- | --- |
| `title`, `doi`, `url`, `journal`, `pmid`, `year`, `key` | Looked up from the Zotero item; field is omitted if empty |
| `today` | Today's date as `YYYY-MM-DD` |
| `authors_wikilink` | First and last authors as `[[Firstname Lastname]]` wikilinks |
| `journal_wikilink` | Journal name wrapped in `[[...]]` |
| `import_wikilink` | `[[key + import filename_suffix]]` — links to the highlights note |
| `reading_wikilink` | `[[key + reading filename_suffix]]` — links to the reading note |
| A YAML list (e.g. `["[[Papers]]"]`) | Static value used verbatim; list elements are themselves resolved |
| Any other string | Static value used verbatim |
| Blank / `null` | Explicit YAML null — renders as `key:` with no value, which Obsidian treats as a boolean checkbox |

### Templates

Templates live in the [templates/](templates/) folder. The template frontmatter is reference-only and is never written to output — the actual frontmatter is always built from `config.yaml`. Only the **body** (content after the second `---`) is read from the template.

#### `templates/highlights.md`

The body of the import note supports three substitution tokens:

| Token | Content |
| --- | --- |
| `{{ABSTRACT}}` | The item's abstract text |
| `{{HIGHLIGHTS}}` | PDF annotations blockquoted with page numbers and optional color emoji |
| `{{NOTES FROM ZOTERO}}` | Standalone Zotero notes, HTML-stripped to plain text |

Any other body content — headings, static text, extra sections — is preserved verbatim. Add or rearrange sections freely.

#### `templates/notes.md`

The body of the reading note is copied verbatim with no substitutions. Edit it to change the default section structure that appears in every new reading note.

## Other resources

This repository stems from me wanting three functionalities:

1. Bulk import all of my highlights
2. Auto creating notes with _similar_, but not exactly the same, properties as my highlight note, which I can then use to write down all of my thoughts.
3. Keeping my Obsidian plugins relatively minimal.

I had Claude mostly write this code for me (thank you).

For a more polished experience, these two Obsidian community plugins are great:

- [obsidian-zoter-integration by Matthew Meyers](https://github.com/obsidian-community/obsidian-zotero-integration)
- [obsidian-zotflow by Xianpi Duan](https://github.com/duanxianpi/obsidian-zotflow)
