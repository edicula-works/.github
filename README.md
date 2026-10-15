# .github da edicula-works

Modelo de PR da organização e job semanal que mantém o Linear em ordem.

## Instalar a edicula (alpha)

Precisa do GitHub CLI (`gh`) com acesso à organização. O instalador baixa a última versão alpha, confere o checksum e roda `edicula alpha setup`, que prepara tudo: Linear, Slack, Orca e agents GLM.

- **Linux, macOS ou WSL:** `curl -fsSL https://raw.githubusercontent.com/edicula-works/.github/main/instalar-edicula.sh | bash`
- **Windows (PowerShell):** `irm https://raw.githubusercontent.com/edicula-works/.github/main/instalar-edicula.ps1 | iex`

Quem trabalha no WSL deve rodar o comando do Linux dentro do WSL. Depois de instalado, `edicula alpha setup` conserta o que faltar e `edicula alpha desligar` volta à versão estável.
