# modules/system/ops/default.nix
{ ... }:
{
  imports = [
    ./common.nix
    ./update.nix
    ./gc.nix
  ];
}
