# Eco-System/modules/userland/ssh-agent-keepassxc.nix
{ config, lib, pkgs, ... }:

with lib;
let
  cfg = config.services.ssh-agent-keepassxc;
in
{
  options.services.ssh-agent-keepassxc.enable =
    mkEnableOption "SSH-Agent (KeePassXC-kompatibel)";

  config = mkIf cfg.enable {
    programs.ssh.startAgent = true;

    environment.etc."environment.d/ssh-agent.conf" = {
    text = "SSH_AUTH_SOCK=$XDG_RUNTIME_DIR/ssh-agent";
    mode = "0644";
};
  };
}
