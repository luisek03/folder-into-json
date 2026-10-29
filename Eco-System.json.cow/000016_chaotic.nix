# modules/system/kernel/cachyos/chaotic.nix
{ config, pkgs, lib, chaotic, ... }:
let
  cfg = config.mySystem.customKernel;

  chaoticPkgs = import chaotic.inputs.nixpkgs {
    inherit (pkgs.stdenv.hostPlatform) system;
    # config = pkgs.config;    ← weglassen, für Cache-Hit
    overlays = [ chaotic.overlays.default ];
  };

  cachyos = if cfg.lts
            then chaoticPkgs.linuxPackages_cachyos-lts
            else chaoticPkgs.linuxPackages_cachyos-lto;
in
{
  imports = [ ./common.nix ];

  config = lib.mkIf cfg.enable {
    # Cache — als Beitrag zur mySystem.caches-Option
    # Selbst wenn base den nyx-cache schon hat: dieses Modul ist autark.
    # Nix dedupliziert beim Schreiben von nix.conf.
    mySystem.caches.substituters = [ "https://nyx-cache.chaotic.cx" ];
    mySystem.caches.trustedKeys  = [ "nyx-cache.chaotic.cx:dJxTrgMC3V3cFfyIiBQDQorG6k1LsqurH/srpMSq7qk=" ];

    mySystem.ops.update.cacheCheck.caches = [ "https://nyx-cache.chaotic.cx" ];

    boot.kernelPackages = cachyos;
    boot.kernel.sysctl."kernel.sched_bore" = 1;
  };
}
