{
  description = "quota-tracker dev environment";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
  };

  outputs = { self, nixpkgs }:
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
      devShells = forAllSystems (
        system:
        let
          pkgs = import nixpkgs {
            inherit system;
            config.allowUnfree = true;
          };
        in
        {
          default = pkgs.mkShell {
            packages = with pkgs; [
              python312
              uv
              nodejs
              gemini-cli
              codex
              github-copilot-cli
              go-task
            ];

            shellHook = ''
              export UV_PROJECT_ENVIRONMENT="$PWD/.venv"
              export PATH="$PWD/.venv/bin:$PWD/node_modules/.bin:$PATH"
              export PYTHONPATH="$PWD''${PYTHONPATH:+:$PYTHONPATH}"

              if [ ! -x "$PWD/.venv/bin/python" ] \
                || [ "$PWD/pyproject.toml" -nt "$PWD/.venv/bin/python" ] \
                || [ "$PWD/uv.lock" -nt "$PWD/.venv/bin/python" ]; then
                echo "[nix] syncing Python dependencies with uv"
                uv sync --extra dev
              fi

              if [ ! -d "$PWD/node_modules" ] \
                || [ "$PWD/package-lock.json" -nt "$PWD/node_modules" ] \
                || [ "$PWD/package.json" -nt "$PWD/node_modules" ]; then
                echo "[nix] installing Node dependencies with npm ci"
                npm ci --no-fund --no-audit
              fi
            '';
          };
        }
      );
    };
}
