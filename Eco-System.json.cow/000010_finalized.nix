# /etc/nixos/Eco-System/modules/finalized.nix
{ config, pkgs, lib, ... }:

{
  # ==========================================
  # (Optional) WEITERE SYSTEMWEITE PAKETE
  # ==========================================
  # Hier kannst du Pakete hinzufügen, die auf ALLEN Hosts
  # installiert sein sollen, aber nicht in default/init.nix stehen.
  # ==========================================
  # environment.systemPackages = with pkgs; [
  #   # ...
  # ];

  nix.settings = {
    extra-substituters        = config.mySystem.caches.substituters;
    extra-trusted-public-keys = config.mySystem.caches.trustedKeys;
  };
}
