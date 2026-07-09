{
  description = "quota-tracker dev environment";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixpkgs-unstable";
    # Do NOT follow our nixpkgs here: numtide's CI builds and caches these
    # packages against their own pinned nixpkgs. Overriding it via `follows`
    # changes the derivation hash and forces a from-source rebuild instead of
    # a cache.numtide.com hit.
    llm-agents.url = "github:numtide/llm-agents.nix";
  };

  outputs = { self, nixpkgs, llm-agents }:
    let
      systems = [
        "x86_64-linux"
        "aarch64-linux"
        "x86_64-darwin"
        "aarch64-darwin"
      ];

      forAllSystems = f: nixpkgs.lib.genAttrs systems (system: f system);
    in
    {
      packages = forAllSystems (
        system:
        let
          pkgs = import nixpkgs { inherit system; };
          quotaTracker = pkgs.callPackage ./nix/package.nix { };
        in
        {
          default = quotaTracker;
          "quota-tracker" = quotaTracker;
        }
      );

      devShells = forAllSystems (
        system:
        let
          pkgs = import nixpkgs {
            inherit system;
            config.allowUnfree = true;
          };

          llmAgents = llm-agents.packages.${system};
        in
        {
          default = pkgs.mkShell {
            packages = [
              (pkgs.python314.withPackages (ps: [ ps.pip ]))
              pkgs.uv
              pkgs.nodejs
              pkgs.go-task

              llmAgents.gemini-cli
              llmAgents.codex
              llmAgents.copilot-cli
              llmAgents.claude-code
              llmAgents.antigravity-cli
              llmAgents.opencode
            ];

            shellHook = ''
              export UV_PROJECT_ENVIRONMENT="$PWD/.venv"
              export PATH="$PWD/.venv/bin:$PWD/node_modules/.bin:$PATH"
              export PYTHONPATH="$PWD''${PYTHONPATH:+:$PYTHONPATH}"

              if [ ! -x "$PWD/.venv/bin/python" ] \
                || [ "$PWD/pyproject.toml" -nt "$PWD/.venv/bin/python" ] \
                || { [ -f "$PWD/uv.lock" ] && [ "$PWD/uv.lock" -nt "$PWD/.venv/bin/python" ]; }; then
                echo "[nix] syncing Python dependencies with uv"
                uv sync --extra dev
              fi

              if [ -f "$PWD/package.json" ] && [ -f "$PWD/package-lock.json" ] && (
                [ ! -d "$PWD/node_modules" ] \
                || [ "$PWD/package-lock.json" -nt "$PWD/node_modules" ] \
                || [ "$PWD/package.json" -nt "$PWD/node_modules" ]
              ); then
                echo "[nix] installing Node dependencies with npm ci"
                npm ci --no-fund --no-audit
              fi
            '';
          };
        }
      );

      nixosModules.default = import ./nix/module.nix;
      homeManagerModules.default = import ./nix/module.nix;
    };
}