# /etc/nixos/flake.nix
{
  description = "Eco-System NixOS configuration";
  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-26.05";

    # Neuer Input für den unstable-Kanal
    nixpkgs-unstable.url = "github:NixOS/nixpkgs/nixos-unstable";
    # Chaotic Nyx — CachyOS-Kernel mit eigenem, aktiv gepflegtem Cache.
    # Liefert v1 (generic) + thinlto + bore aus dem Cache.
    # Custom-Varianten (v3, zen2, full-lto) werden lokal gebaut
    # via cachyOverride in den jeweiligen Kernel-Modulen.
    chaotic.url = "github:chaotic-cx/nyx/nyxpkgs-unstable";
  };

  # NEU: nixpkgs-unstable in den Argumenten
  outputs = { self, nixpkgs, nixpkgs-unstable, chaotic, ... }:
    let
      system = "x86_64-linux";
      hostConfig = import ./host-config.nix;

      # NEU: Overlay, das pkgs.unstable bereitstellt.
      # Damit kann jedes Modul/Profil gezielt Pakete aus dem
      # unstable-Kanal beziehen (z. B. pkgs.unstable.keepassxc),
      # während das restliche System auf 26.05 bleibt.
      overlay-unstable = final: prev: {
        unstable = import nixpkgs-unstable {
          inherit system;
          config = prev.config;   # allowUnfree etc. erben
        };
      };

      # Nur chaotic wird als extra-Argument an die Module gereicht.
      # Alle kernel/cachyos/*.nix-Dateien erwarten `chaotic`.
      commonArgs = {
        inherit chaotic;
      };
    in
    {
      nixosConfigurations = {
        ${hostConfig.name} = nixpkgs.lib.nixosSystem {
          system = "x86_64-linux";
          modules = [
            # NEU: Overlay laden, bevor configuration.nix greift
            { nixpkgs.overlays = [ overlay-unstable ]; }
            ./configuration.nix
          ];
          specialArgs = commonArgs;
        };

        default = nixpkgs.lib.nixosSystem {
          system = "x86_64-linux";
          modules = [
            # NEU: Overlay laden, bevor configuration.nix greift
            { nixpkgs.overlays = [ overlay-unstable ]; }
            ./configuration.nix
          ];
          specialArgs = commonArgs;
        };
      };
    };
}
