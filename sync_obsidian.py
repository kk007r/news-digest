from __future__ import annotations

import argparse
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    import yaml
except ModuleNotFoundError as exc:
    print(f"必要なライブラリが見つかりません: {exc.name}")
    print("先に `pip install -r requirements.txt` を実行してください。")
    raise SystemExit(1) from exc


BASE_DIR = Path(__file__).resolve().parent
NEWS_DIR = BASE_DIR / "news"
DEFAULT_CONFIG_PATH = BASE_DIR / "obsidian.yml"
LOCAL_CONFIG_PATH = BASE_DIR / "obsidian.local.yml"


@dataclass(frozen=True)
class SyncConfig:
    vault_path: Path
    target_folder: str
    overwrite: bool


def load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as file:
        data = yaml.safe_load(file) or {}
    if not isinstance(data, dict):
        raise ValueError(f"YAMLの形式が正しくありません: {path}")
    return data


def merge_config(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if value is not None:
            merged[key] = value
    return merged


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="生成済みMarkdownをObsidian保管庫へコピーします。")
    parser.add_argument("--vault", help="Obsidian保管庫のパス。例: <Obsidian保管庫のパス>")
    parser.add_argument("--target-folder", help="保管庫内のコピー先フォルダ。既定: News Digest")
    parser.add_argument("--no-overwrite", action="store_true", help="同名ファイルがある場合は上書きしません。")
    parser.add_argument("--dry-run", action="store_true", help="コピーせず、実行予定だけ表示します。")
    return parser.parse_args()


def build_config(args: argparse.Namespace) -> SyncConfig:
    config = load_yaml(DEFAULT_CONFIG_PATH)
    config = merge_config(config, load_yaml(LOCAL_CONFIG_PATH))

    cli_config: dict[str, Any] = {}
    if args.vault:
        cli_config["vault_path"] = args.vault
    if args.target_folder:
        cli_config["target_folder"] = args.target_folder
    if args.no_overwrite:
        cli_config["overwrite"] = False
    config = merge_config(config, cli_config)

    vault_value = str(config.get("vault_path", "")).strip()
    if not vault_value:
        raise SystemExit("Obsidian保管庫のパスが未設定です。obsidian.local.yml か --vault で指定してください。")

    target_folder = str(config.get("target_folder", "News Digest")).strip().strip("/\\")
    if not target_folder:
        raise SystemExit("target_folder が空です。")

    return SyncConfig(
        vault_path=Path(vault_value).expanduser(),
        target_folder=target_folder,
        overwrite=bool(config.get("overwrite", True)),
    )


def iter_markdown_files() -> list[Path]:
    if not NEWS_DIR.exists():
        raise SystemExit(f"同期元フォルダが見つかりません: {NEWS_DIR}")
    return sorted(path for path in NEWS_DIR.rglob("*.md") if path.is_file())


def ensure_destination_is_safe(vault_path: Path, destination_root: Path) -> tuple[Path, Path]:
    resolved_vault = vault_path.resolve()
    if not resolved_vault.exists():
        raise SystemExit(f"Obsidian保管庫が見つかりません: {resolved_vault}")
    if not resolved_vault.is_dir():
        raise SystemExit(f"Obsidian保管庫がフォルダではありません: {resolved_vault}")

    resolved_destination = destination_root.resolve()
    if resolved_destination != resolved_vault and resolved_vault not in resolved_destination.parents:
        raise SystemExit(f"コピー先が保管庫の外です: {resolved_destination}")
    return resolved_vault, resolved_destination


def sync_to_obsidian(config: SyncConfig, dry_run: bool) -> None:
    destination_root = config.vault_path / config.target_folder
    resolved_vault, resolved_destination = ensure_destination_is_safe(config.vault_path, destination_root)
    markdown_files = iter_markdown_files()

    print(f"Obsidian保管庫: {resolved_vault}")
    print(f"コピー先: {resolved_destination}")
    print(f"同期対象: {len(markdown_files)}件")
    if not (resolved_vault / ".obsidian").exists():
        print("[warn] 指定フォルダ内に .obsidian が見つかりません。保管庫パスが正しいか確認してください。")

    for source in markdown_files:
        relative_path = source.relative_to(NEWS_DIR)
        destination = resolved_destination / relative_path
        exists = destination.exists()
        if exists and not config.overwrite:
            print(f"[skip] {relative_path}")
            continue

        if dry_run:
            action = "overwrite" if exists else "copy"
            print(f"[dry-run:{action}] {relative_path}")
            continue

        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        action = "overwrite" if exists else "copy"
        print(f"[{action}] {relative_path}")


def main() -> None:
    args = parse_args()
    config = build_config(args)
    sync_to_obsidian(config, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
