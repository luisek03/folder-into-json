# modules/system/kernel/lts.nix
{ config, pkgs, lib, ... }:
{
  imports = [ ./_options.nix ];

  config = lib.mkIf (!config.mySystem.customKernel.enable) {
    # NixOS-Standard-Kernel = neuester LTS.
    # Wenn kein Custom-Kernel aktiv ist, greift dieser Fallback.
    boot.kernelPackages = pkgs.linuxPackages;
  };
}
