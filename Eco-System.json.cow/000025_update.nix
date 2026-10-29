# modules/system/ops/update.nix
{ config, pkgs, lib, ... }:

let
  cfg = config.mySystem.ops.update;
  backup = cfg.flakeLockBackup;
  hook = cfg.postUpdate;

  # --cache-urls nur setzen, wenn Caches konfiguriert sind.
  # Sonst bricht argparse ab („expected one argument").
  cacheUrlsArg =
    lib.optionalString (cfg.cacheCheck.caches != [])
      "--cache-urls ${lib.concatStringsSep "," cfg.cacheCheck.caches}";

  ecoUpdate = pkgs.writeShellApplication {
    name = "eco-update";
    runtimeInputs = with pkgs; [ python3 nix git curl coreutils nix-output-monitor ];
    text = ''
      exec python3 ${./update} \
        --user ${config.mySystem.userName} \
        --retries ${toString cfg.retries} \
        --delay ${toString cfg.retryDelay} \
        --cache-check ${if cfg.cacheCheck.enable then "1" else "0"} \
        ${cacheUrlsArg} \
        --backup ${if backup.enable then "1" else "0"} \
        --backup-repo ${backup.repoPath} \
        --backup-commit ${if backup.autoCommit then "1" else "0"} \
        --backup-msg ${lib.escapeShellArg backup.commitMessage} \
        --git-author-name ${lib.escapeShellArg backup.gitAuthorName} \
        --git-author-email ${lib.escapeShellArg backup.gitAuthorEmail} \
        --hook ${if hook.enable then "1" else "0"} \
        --hook-script ${lib.escapeShellArg (hook.script or "")} \
        "$@"
    '';
  };
in
{
  config = lib.mkIf cfg.enable {
    environment.systemPackages = [ ecoUpdate ];
  };
}
