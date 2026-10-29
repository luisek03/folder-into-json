# /etc/nixos/configuration.nix
{ config, pkgs, lib, ... }:

let
  hostConfig = import ./host-config.nix;
  hostPath = ./hosts/${hostConfig.host};
in
{
  # Sicherheitscheck: Host-Ordner muss existieren
  assertions = [
    {
      assertion = builtins.pathExists hostPath;
      message = "Host '${hostConfig.host}' existiert nicht unter Eco-System/hosts/!";
    }
  ];

  imports = [
    ./modules/init.nix
    # ./default/init.nix   ← ENTFERNT (jetzt profile/base + profile/luis-eco)
    hostPath
    ./modules/finalized.nix
  ];
}
