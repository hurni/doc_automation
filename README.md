# 📚 Documentation Build System

A lightweight documentation build tool that transforms structured glossary terms into consistent, versioned documentation across Markdown and SVG files.

It supports:
- YAML-based terminology management
- automatic term replacement in docs
- schema validation
- incremental builds
- archive/version history
- restore and version inspection modes
- dry-run preview mode

---

# 🧠 Core concept

Instead of writing raw text:

    The customer creates an order.

you write structured placeholders:

    The {{term:customer}} creates an {{term:order}}.

During build, these placeholders are resolved using a central glossary (`terms.yaml`).

This ensures:
- consistent terminology across all docs
- easy refactoring of domain language
- single source of truth for definitions

---

# 📁 Project structure

    .
    ├── build_docs.py
    ├── terms.yaml
    ├── terms.json
    ├── docs/
    │   ├── *.md
    │   └── *.svg
    ├── archive/
    └── .build_cache.json

---

# 📦 Glossary format (`terms.yaml`)

The glossary is defined in YAML:

    terms:
      customer:
        label: Customer
        definition: A person or organization that buys products

      order:
        label: Order
        definition: A customer request to purchase products

Each term should include:

- label → display name used in documentation
- definition → description of the concept

---

# ⚙️ Template syntax

Basic usage:
```
    {{term:customer}} → inserts "Customer"
    {{term:order}} → inserts "Order"
```

Attribute access:

```
    {{term:order.definition}} → inserts definition
    {{term:customer.label}} → inserts label explicitly
```

---

# 🚀 CLI usage

## Build documentation
```
    python build_docs.py
```

Behavior:
- processes all `.md` and `.svg` files in `docs/`
- replaces all term placeholders
- archives files before modification
- runs incrementally (skips unchanged files)
- fails on unknown terms (strict mode by default)

---

## Dry run mode
```
    python build_docs.py --dry-run
    python build_docs.py -dr
```

Behavior:
- shows changes as a diff
- does NOT modify any files
- useful for validation and review

---

## Force mode
```
    python build_docs.py --force
    python build_docs.py -f
```

Behavior:
- allows unknown terms
- continues build instead of failing
- replaces missing values with placeholders like:
  [UNKNOWN:term]

---

## Restore latest archived version

```
    python build_docs.py --restore docs/api/order.md
    python build_docs.py -r docs/api/order.md
```

Behavior:
- restores the most recent archived version
- overwrites current file

---

## List available versions

```
    python build_docs.py --multi-version-restore docs/api/order.md
    python build_docs.py -R docs/api/order.md
```
    
Behavior:
- lists all archived versions
- shows timestamps
- does not modify files

---

# 📦 Archive system

Before modifying files, backups are stored in:

    `archive/`

Example:

```
    archive/docs/api/
      20260410_142301_123456_order.md
      20260410_150012_654321_order.md
```
      
Features:
- preserves folder structure
- microsecond timestamps
- full rollback history

---

# ⚡ Incremental builds

Only changed files are processed using:

- file hash comparison
- cached build state (.build_cache.json)
- glossary change detection

This ensures fast builds.

---

# 🛡 Validation system

Before building, the system validates `terms.yaml`.

Required:

- label (string)
- definition (string)

Failures:
- missing terms root key
- missing required fields
- invalid field types
- unknown terms (unless --force is used)

---

# 🧾 Supported formats

- Markdown (.md)
- SVG (.svg)

---

# 🧭 Recommended workflow

```

    # preview changes
    python build_docs.py -dr

    # build
    python build_docs.py

    # inspect history
    python build_docs.py -R docs/file.md

    # restore version
    python build_docs.py -r docs/file.md
    
```

---

# 🧠 Design philosophy

- single source of truth (YAML glossary)
- explicit references (no hidden replacements)
- safe automation (archive before changes)
- reproducibility (incremental builds)
- inspectability (history + dry-run)

---

# 📌 Summary

This tool standardizes terminology across documentation and enables safe, versioned refactoring at scale.
