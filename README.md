# template-python-strict

Python 3 devcontainer で、安全性に配慮しつつ厳密な型チェックを行うためのテンプレートです。

## 目的

- Python 3 系の開発環境を devcontainer で再現可能にする
- 非 root 実行と最小権限で開発コンテナを運用する
- VS Code で Python 開発に有用な拡張を標準化する
- Pyright strict による厳密な型チェックを常時有効にする

## セットアップ

1. このリポジトリを VS Code で開く
2. `Dev Containers: Rebuild and Reopen in Container` を実行する
3. コンテナ初回起動後、`postCreateCommand` で `.venv` と開発ツールが導入される

## 含まれる主な設定

- `.devcontainer/devcontainer.json`
  - `remoteUser: vscode` による非 root 実行
  - `--cap-drop=ALL` と `no-new-privileges:true` を付与
  - Python / Pylance / Ruff などの拡張をコンテナ側で自動適用
- `.devcontainer/Dockerfile`
  - `mcr.microsoft.com/devcontainers/python` ベース
  - 余分な OS パッケージ導入を避ける最小構成
- `pyproject.toml`
  - `tool.pyright` の `typeCheckingMode = "strict"`
  - Ruff の lint/format 設定
- `.vscode/settings.json`
  - workspace でも strict 診断を有効化
  - 保存時に Ruff の fix/import 整理を適用

## 型チェックと lint 実行

コンテナ内で以下を実行:

```bash
./.venv/bin/pyright
./.venv/bin/ruff check .
./.venv/bin/ruff format .
```

## セキュリティ方針

- コンテナ内作業は非 root ユーザーを基本とする
- Linux capabilities は原則 drop し、不要な権限を与えない
- 依存更新時はバージョン固定を前提にレビューして反映する

## VS Code 推奨拡張

- ms-python.python
- ms-python.vscode-pylance
- charliermarsh.ruff
- tamasfe.even-better-toml
- ms-azuretools.vscode-docker
- github.vscode-github-actions
