# modules/features/gaming/default.nix
{ ... }:

{
  imports = [
    ./common.nix
    ./steam.nix
    # ./lutris.nix    # später
    # ./heroic.nix    # später
  ];
}
