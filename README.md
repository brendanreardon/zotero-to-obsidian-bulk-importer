# Zotero to Obsidian Bulk Importer

A script that syncs your Zotero library into an Obsidian vault by reading directly from Zotero's local SQLite database.

For each qualifying item, the script creates two notes:

- An **import note** in a literature folder containing YAML frontmatter, the abstract, inline annotations extracted from PDFs, and any standalone Zotero notes. These notes are fully managed by the script and overwritten on each run.
- A **reading note** in a reading notes folder containing frontmatter and empty section headers for your own writing. This is created once and never overwritten.

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

Before running the script, edit the five configuration variables at the top of [zotero_to_obsidian.py](zotero_to_obsidian.py):

| Variable | Description | Default |
|---|---|---|
| `ZOTERO_DB` | Path to `zotero.sqlite` | `~/Zotero/zotero.sqlite` |
| `OBSIDIAN_VAULT` | Path to your Obsidian vault root | `~/path/to/your/vault` |
| `LITERATURE_DIR` | Subfolder name for import notes | `Literature` |
| `READING_DIR` | Subfolder name for reading notes | `Reading Notes` |
| `FILENAME_FORMAT` | Filename pattern, truncated to 80 characters | `{author} {year} - {title}` |

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

The script is safe to run repeatedly. Import notes are always overwritten with fresh data from Zotero. Reading notes are only created if no existing file in `READING_DIR` already has a matching `zotero_key` in its frontmatter, so any notes you have written will never be touched.

The script can be run while Zotero is open.
