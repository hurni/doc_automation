import yaml
import json
import re
import argparse
import difflib
from pathlib import Path
import sys
import shutil
from datetime import datetime
import hashlib

# ------------------------
# PATH SETUP
# ------------------------

BASE_DIR = Path(__file__).parent.resolve()

INPUT_YAML = BASE_DIR / "terms.yaml"
OUTPUT_JSON = BASE_DIR / "terms.json"

DOCS_INPUT_DIR = BASE_DIR / "docs/input"
DOCS_OUTPUT_DIR = BASE_DIR / "docs/output"

ARCHIVE_DIR = BASE_DIR / "archive"
CACHE_FILE = BASE_DIR / ".build_cache.json"

# ------------------------
# PATTERNS
# ------------------------

VAR_PATTERN = r"\{\{([a-zA-Z0-9_\.]+)\}\}"
LOOP_PATTERN = r"\{\{for ([a-zA-Z0-9_]+) in ([a-zA-Z0-9_\.]+)\}\}(.*?)\{\{endfor\}\}"
IF_PATTERN = r"\{\{if ([a-zA-Z0-9_\.]+)\}\}(.*?)\{\{endif\}\}"

REQUIRED_FIELDS = ["label", "definition"]
REFERENCE_FIELDS = ["related", "processes"]

# ------------------------
# UTILS
# ------------------------

def file_hash(path):
    return hashlib.md5(path.read_bytes()).hexdigest()

def load_cache():
    if CACHE_FILE.exists():
        return json.loads(CACHE_FILE.read_text())
    return {}

def save_cache(cache):
    CACHE_FILE.write_text(json.dumps(cache, indent=2))

# ------------------------
# YAML / VALIDATION
# ------------------------

def load_yaml():
    return yaml.safe_load(INPUT_YAML.read_text())

def save_json(data):
    OUTPUT_JSON.write_text(json.dumps(data, indent=2))

def validate_schema(data):
    errors = []

    if "terms" not in data:
        return ["Missing 'terms' root"]

    for key, term in data["terms"].items():
        for field in REQUIRED_FIELDS:
            if field not in term:
                errors.append(f"{key} missing '{field}'")

    return errors


def validate_references(terms):
    errors = []

    for term_name, term in terms.items():
        for field in REFERENCE_FIELDS:
            if field in term:
                for ref in term[field]:
                    if ref not in terms:
                        errors.append(
                            f"{term_name}.{field} -> unknown reference '{ref}'"
                        )

    return errors

# ------------------------
# LINKING
# ------------------------

def make_link(term_key, terms):
    label = terms[term_key]["label"]
    return f"[{label}]({term_key}.md)"

# ------------------------
# ARCHIVE
# ------------------------

def archive_file(path):
    relative = path.relative_to(DOCS_OUTPUT_DIR)

    timestamp = datetime.fromtimestamp(path.stat().st_mtime)\
        .strftime("%Y%m%d_%H%M%S_%f")

    target_dir = ARCHIVE_DIR / relative.parent
    target_dir.mkdir(parents=True, exist_ok=True)

    target_file = target_dir / f"{timestamp}_{path.name}"

    shutil.copy2(path, target_file)

# ------------------------
# RESTORE
# ------------------------

def restore_file(target):
    target = Path(target)

    relative = target.relative_to(DOCS_OUTPUT_DIR)
    archive_dir = ARCHIVE_DIR / relative.parent

    versions = sorted(archive_dir.glob(f"*_{target.name}"))

    if not versions:
        print("No archive found")
        sys.exit(1)

    latest = versions[-1]
    shutil.copy2(latest, target)

    print(f"Restored: {target}")

def list_versions(target):
    target = Path(target)

    relative = target.relative_to(DOCS_OUTPUT_DIR)
    archive_dir = ARCHIVE_DIR / relative.parent

    versions = sorted(archive_dir.glob(f"*_{target.name}"))

    print(f"\nVersions for {target}:\n")

    for i, v in enumerate(versions):
        print(f"[{i}] {v.name}")

# ------------------------
# TEMPLATE ENGINE
# ------------------------

def resolve_path(path, terms, errors, local_ctx=None):
    parts = path.split(".")

    if local_ctx and parts[0] in local_ctx:
        value = local_ctx[parts[0]]
        parts = parts[1:]

        if isinstance(value, str) and value in terms:
            value = terms[value]
    else:
        term = parts[0]

        if term not in terms:
            errors.add(term)
            return None

        value = terms[term]
        parts = parts[1:]

    for attr in parts:
        if isinstance(value, dict) and attr in value:
            value = value[attr]
        else:
            errors.add(path)
            return None

    return value


def replace_variables(text, terms, errors, local_ctx=None):
    def repl(match):
        path = match.group(1)
        value = resolve_path(path, terms, errors, local_ctx)

        if value is None:
            return f"[UNKNOWN:{path}]"

        if isinstance(value, list):
            rendered = []
            for item in value:
                if isinstance(item, str) and item in terms:
                    rendered.append(make_link(item, terms))
                else:
                    rendered.append(str(item))
            return ", ".join(rendered)

        if isinstance(value, str) and value in terms:
            return make_link(value, terms)

        return str(value)

    return re.sub(VAR_PATTERN, repl, text)


def process_conditionals(text, terms, errors, local_ctx=None):
    def repl(match):
        condition = match.group(1)
        body = match.group(2)

        value = resolve_path(condition, terms, errors, local_ctx)

        if value:
            return render(body, terms, errors, local_ctx)
        return ""

    return re.sub(IF_PATTERN, repl, text, flags=re.DOTALL)


def process_loops(text, terms, errors, local_ctx=None):
    def repl(match):
        var_name = match.group(1)
        iterable_path = match.group(2)
        body = match.group(3)

        iterable = resolve_path(iterable_path, terms, errors, local_ctx)

        if not isinstance(iterable, list):
            errors.add(iterable_path)
            return f"[NOT_A_LIST:{iterable_path}]"

        result = []

        for item in iterable:
            ctx = dict(local_ctx or {})
            ctx[var_name] = item

            rendered = render(body, terms, errors, ctx)
            result.append(rendered.strip())

        return "\n".join(result)

    return re.sub(LOOP_PATTERN, repl, text, flags=re.DOTALL)


def render(text, terms, errors, local_ctx=None):
    prev = None

    while text != prev:
        prev = text
        text = process_loops(text, terms, errors, local_ctx)
        text = process_conditionals(text, terms, errors, local_ctx)
        text = replace_variables(text, terms, errors, local_ctx)

    return text

# ------------------------
# PROCESS FILES
# ------------------------

def process_file(
    input_path,
    output_path,
    terms,
    cache,
    terms_hash,
    force=False,
    dry_run=False
):
    errors = set()

    input_hash = file_hash(input_path)

    cache_entry = cache.get(str(input_path), {})

    # backward compatibility
    if isinstance(cache_entry, str):
        cache_entry = {
            "input_hash": cache_entry,
            "terms_hash": None
        }

    # incremental build check
    if (
        not force
        and cache_entry.get("input_hash") == input_hash
        and cache_entry.get("terms_hash") == terms_hash
    ):
        return errors

    original = input_path.read_text()
    updated = render(original, terms, errors)

    output_path.parent.mkdir(parents=True, exist_ok=True)

    existing = output_path.read_text() if output_path.exists() else None

    if existing != updated:
        if dry_run:
            print(f"\n--- {output_path} (DRY RUN) ---")
            diff = difflib.unified_diff(
                (existing or "").splitlines(),
                updated.splitlines(),
                lineterm=""
            )
            print("\n".join(diff))
        else:
            if output_path.exists():
                archive_file(output_path)

            output_path.write_text(updated)
            print(f"Built: {output_path}")

    # update cache
    cache[str(input_path)] = {
        "input_hash": input_hash,
        "terms_hash": terms_hash
    }

    return errors


def process_docs(terms, cache, terms_hash, force=False, dry_run=False):
    all_errors = set()

    for input_file in DOCS_INPUT_DIR.rglob("*"):
        if input_file.suffix not in [".md", ".svg"]:
            continue

        rel = input_file.relative_to(DOCS_INPUT_DIR)
        output_file = DOCS_OUTPUT_DIR / rel

        errors = process_file(
            input_file,
            output_file,
            terms,
            cache,
            terms_hash,
            force,
            dry_run
        )

        all_errors.update(errors)

    return all_errors

# ------------------------
# MAIN
# ------------------------

def main():
    parser = argparse.ArgumentParser()

    parser.add_argument("--force", "-f", action="store_true")
    parser.add_argument("--dry-run", "-dr", action="store_true")
    parser.add_argument("--restore", "-r", type=str)
    parser.add_argument("--multi-version-restore", "-R", type=str)

    args = parser.parse_args()

    if args.restore:
        restore_file(args.restore)
        return

    if args.multi_version_restore:
        list_versions(args.multi_version_restore)
        return

    data = load_yaml()

    schema_errors = validate_schema(data)
    if schema_errors:
        print("Schema errors:")
        for e in schema_errors:
            print("-", e)
        sys.exit(1)

    save_json(data)

    terms = data["terms"]

    ref_errors = validate_references(terms)
    if ref_errors:
        print("Reference validation failed:")
        for e in ref_errors:
            print("-", e)
        sys.exit(1)

    cache = load_cache()

    terms_hash = file_hash(INPUT_YAML)

    errors = process_docs(
        terms,
        cache,
        terms_hash,
        force=args.force,
        dry_run=args.dry_run
    )

    cache["_terms_hash"] = terms_hash
    save_cache(cache)

    if errors:
        print("\nUnknown terms:")
        for e in sorted(errors):
            print("-", e)

        if not args.force:
            sys.exit(1)

    print("\nDone")


if __name__ == "__main__":
    main()
