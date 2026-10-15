#!/usr/bin/env bash
# Instala o edicula alpha (Linear + Slack + Orca + agents GLM) e roda o setup.
# Uso: curl -fsSL https://raw.githubusercontent.com/edicula-works/.github/main/instalar-edicula.sh | bash
# Linux, macOS e WSL. Precisa do GitHub CLI (gh) com acesso à organização edicula-works.
set -euo pipefail

if ! command -v gh >/dev/null 2>&1; then
  echo "Instale o GitHub CLI primeiro: https://cli.github.com (depois rode este comando de novo)." >&2
  exit 1
fi
if ! gh auth status -h github.com >/dev/null 2>&1; then
  echo "Entrando no GitHub (abre o navegador ou mostra um código)..."
  gh auth login -h github.com -w -p https </dev/tty
fi

case "$(uname -s)-$(uname -m)" in
  Linux-x86_64) asset=edicula-linux-x64 ;;
  Linux-aarch64|Linux-arm64) asset=edicula-linux-arm64 ;;
  Darwin-arm64) asset=edicula-darwin-arm64 ;;
  Darwin-x86_64) asset=edicula-darwin-x64 ;;
  *) echo "Sistema não suportado: $(uname -s) $(uname -m)" >&2; exit 1 ;;
esac

tag=$(gh release list -R edicula-works/harness --limit 50 --json tagName,isPrerelease \
  --jq '[.[] | select(.isPrerelease and (.tagName | test("^v[0-9.]+-alpha\\.[0-9]+$")))] | sort_by(.tagName | sub("^v[0-9.]+-alpha\\."; "") | tonumber) | last | .tagName')
[ -n "$tag" ] && [ "$tag" != "null" ] || { echo "Não achei a versão alpha (sem acesso ao repo edicula-works/harness?)" >&2; exit 1; }

tmp=$(mktemp -d); trap 'rm -rf "$tmp"' EXIT
echo "Baixando edicula $tag ($asset)..."
gh release download "$tag" -R edicula-works/harness -p "$asset" -p SHA256SUMS -D "$tmp"
( cd "$tmp" && grep " $asset\$" SHA256SUMS | sha256sum -c - >/dev/null 2>&1 || grep " $asset\$" SHA256SUMS | shasum -a 256 -c - >/dev/null ) \
  || { echo "Checksum não confere; abortando." >&2; exit 1; }
chmod 755 "$tmp/$asset"
# O setup instala o binário no lugar certo (guardando o estável) e prepara tudo.
"$tmp/$asset" alpha setup </dev/tty
