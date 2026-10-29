# modules/system/kernel/cachyos/lto-v3.nix
{ config, pkgs, lib, chaotic, ... }:
let
  cfg = config.mySystem.customKernel;

  # Eigene pkgs-Instanz aus chaotic's nixpkgs.
  # Diese Instanz ist IDENTISCH mit dem, was chaotic zum Bauen nutzt
  # → gleicher Hash → Cache-Hit.
  chaoticPkgs = import chaotic.inputs.nixpkgs {
    inherit (pkgs.stdenv.hostPlatform) system;
    # config = pkgs.config;    ← weglassen
    overlays = [ chaotic.overlays.default ];
  };

  base = chaoticPkgs.linuxPackages_cachyos-lto;
in
{
  imports = [ ./common.nix ];

  config = lib.mkIf cfg.enable {
    # lto-v3 hat keinen eigenen Cache (wird immer lokal gebaut),
    # aber die nyx-cache-Substituter bleiben für die Abhängigkeiten
    # des Kernels (kmod, linux-firmware, …) relevant.
    mySystem.caches.substituters = [ "https://nyx-cache.chaotic.cx" ];
    mySystem.caches.trustedKeys  = [ "nyx-cache.chaotic.cx:dJxTrgMC3V3cFfyIiBQDQorG6k1LsqurH/srpMSq7qk=" ];

    boot.kernelPackages = base.cachyOverride {
      cachyVars = base.kernel.cachyConfig.cachyVars // {
        "_processor_opt" = "GENERIC_V3";
        "_use_llvm_lto" = "thin";
      };
    };

    boot.kernel.sysctl."kernel.sched_bore" = 1;
  };
}
