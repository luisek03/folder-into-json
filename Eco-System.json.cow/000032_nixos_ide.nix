# /etc/nixos/Eco-System/modules/userland/nixos_ide.nix
{ config, pkgs, lib, ... }:

let
  cfg = config.mySystem.ide;

  # rsync-Argumente aus der exclude-Liste bauen.
  # escapeShellArg, damit Pfade mit Sonderzeichen nicht brechen.
  rsyncExcludes = lib.concatMapStringsSep " "
    (e: "--exclude=${lib.escapeShellArg e}")
    cfg.exclude;
in
{
  options.mySystem.ide = {
    enable = lib.mkOption {
      type = lib.types.bool;
      default = false;
      description = "Enable IDE setup (Kate + Git + Nix-LSP).";
    };
    repoUrl = lib.mkOption {
      type = lib.types.str;
      default = "https://github.com/deinuser/Eco-System.git";
      description = "Git repository URL for cloning (SSH or HTTPS).";
    };
    repoPath = lib.mkOption {
      type = lib.types.str;
      default = "/home/luisek03/Projekte/Eco-System";
      description = "Pfad zum Eco-System-Repo (Projekt-Root, nicht OS-Root).";
    };
    userName = lib.mkOption {
      type = lib.types.str;
      default = "luisek03";
      description = "Username for the home directory path.";
    };
    exclude = lib.mkOption {
      type = lib.types.listOf lib.types.str;
      default = [
        # Host-spezifisch — /etc/nixos darf diese NICHT überschreiben
        "host-config.nix"
        "hardware-configuration.nix"

        # flake.lock: /etc/nixos ist die "lebende" Instanz (eco-upgrade
        # aktualisiert sie dort). Repo-lock dient nur als Bootstrap.
        "flake.lock"

        # Git & Build-Artefakte
        ".git"
        ".gitignore"
        "result"
        "result-*"
        "*.drv"

        # DOCS musst jz nicht unbedingt in /etc/nixos
        # es würde aber auch nicht schaden da nicht aktiviert wird.
        "docs"
        "README.md"

        # Editor-Kram
        "*.swp"
        "*.kate-swp"
        "*~"
        ".DS_Store"
        ".directory"
      ];
      description = "Files to exclude from rsync when deploying to /etc/nixos.";
    };
  };

  config = lib.mkIf cfg.enable {

    environment.systemPackages = with pkgs; [
      nixd
      git
      lazygit
      gh

      kdePackages.kate
    ];

    # ==========================================
    # WORKFLOW-ALIASES
    # ==========================================
    environment.shellAliases = {
      eco        = "cd ${cfg.repoPath}";
      eco-edit   = "current_dir=$(pwd) && cd ${cfg.repoPath} && kate . && cd $current_dir";
      eco-status = "cd ${cfg.repoPath} && git status";
      eco-commit = "cd ${cfg.repoPath} && git add . && git commit -m \"Update $(date +'%Y-%m-%d %H:%M')\"";
      eco-push   = "cd ${cfg.repoPath} && git push";
      eco-pull   = ''
        cd ${cfg.repoPath}
        if ! git diff-index --quiet HEAD --; then
          echo "⚠️  Uncommittete Änderungen vorhanden – bitte erst committen!"
          git status --short
          exit 1
        fi
        git pull --rebase
      '';
      eco-log    = "cd ${cfg.repoPath} && git log --oneline --graph --all";

      # ------------------------------------------
      # DEPLOY (Flakes, Build aus /etc/nixos)
      # ------------------------------------------
      deploy-dry = ''
        echo "Copying Eco-System configuration to /etc/nixos (dry-run)..."
        sudo rsync -av --delete ${rsyncExcludes} ${cfg.repoPath}/Eco-System/ /etc/nixos/

        echo "Running nixos-rebuild dry-run (flake)..."
        sudo nixos-rebuild dry-run --flake /etc/nixos
      '';

      deploy = ''
        echo "Copying Eco-System configuration to /etc/nixos..."
        sudo rsync -av --delete ${rsyncExcludes} ${cfg.repoPath}/Eco-System/ /etc/nixos/

        echo "Running nixos-rebuild switch (flake)..."
        sudo nixos-rebuild switch --flake /etc/nixos
      '';

      deploy-copy = "sudo rsync -av --delete ${rsyncExcludes} ${cfg.repoPath}/Eco-System/ /etc/nixos/";
    };
  };
}
