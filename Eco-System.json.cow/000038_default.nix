# /etc/nixos/Eco-System/profile/luis-eco/default.nix
# ==========================================
# LUIS' PERSÖNLICHER WUNSCH
# ==========================================
# Skalare: lib.mkDefault (überschreibt profile/base, wird von Host überstimmt)
# Listen/Attrsets: lib.mkDefault (merge mit profile/base + Host)
# ==========================================

{ config, pkgs, lib, ... }:

{
  imports = [
    ../../modules/userland/ssh-agent-keepassxc.nix
  ];

  config = {
    # ==========================================
    # SSH-AGENT (persönliche Entscheidung)
    # ==========================================
    services.ssh-agent-keepassxc.enable = lib.mkDefault false;
    # Überarbeitung geplant: KeepassXC als System-Standard statt Kwallet;
    # OS soll nur in gerätespezifischen Ordner schreiben, Export-Skript
    # für mit Tag markierte Public Keys (siehe Notizen).

    # ==========================================
    # USER-DEFINITION (nur hier, nicht in base)
    # ==========================================
    users.users.luisek03 = {
      isNormalUser = lib.mkDefault true;
      group        = lib.mkDefault "users";
      description  = lib.mkDefault "Luis Fernando Meyer";
      extraGroups  = lib.mkDefault [ "networkmanager" "wheel" ];
      openssh.authorizedKeys.keys = lib.mkDefault [
        "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAACAQCXLMiJQ3qbA+A00WMbhsDjUbueKZz5UsL8YnOLmJI7hJefP1f/HXixGYyA9qQiRU8rpezkscUzFdtFSFhMEzTkwA5J8n5p5BaPGCXoqTqxfjGFKsHEIuvQdbrIu4hCsEIAT86veTv4gCv/0cMvlUli1fkihikrZD8If0YQKFl0mg4AS0Ay1aXeCJ7Xzfwe0+CmjjK+GK+igA7YIl6GMDXZHSuaiKC623anW21+ArEZmh7QYwKsWSGhf63DcuVKNJBOxh+bm9g/t+inv8aMZKLlguURjMvnV37V6KFDOm3SG26gynU2u6DnQ/VaP7sX5aJ/kqt1svsAqGOREKt2IgVnlbdnv36TrikInm8YHde/hqc2gJhRSymmzsBfKysQxFqfWbRDA/i7EpCp+9X78Zo1NCkupakAmqvBNvpKxkRamT8vTTOxyrhy+W0mIgtHzh4VF9J4URX8j8joo/LIGk+p7UUT6BSNsTwMiYzpgLRWb4GFhyDwyzv2iJOknxjg5V+unT7ZZSPYKwrdMxV8Co6geFzOnzQfBSmppgjub6yEIMvJG6t80V2R06TLKjvpIwsXSSx4+sOk6/tcHCJxCmRQi72B3o1NPb5M+UU76yDRePayCeQyuQU2UW8PVJycuiSRU0J07iwdncTWWHQiZkqV/8NZXCwbCe/MhQ4vgDlnrw== luisek03@Nexte"
      ];
      #packages = lib.mkDefault (with pkgs; [
      #  kdePackages.kate
      #]);
    };

    # ==========================================
    # LOCALE (Deutsch — überschreibt base "en_US")
    # ==========================================
    time.timeZone      = lib.mkDefault "Europe/Berlin";
    i18n.defaultLocale = lib.mkDefault "de_DE.UTF-8";
    i18n.extraLocaleSettings = lib.mkDefault {
      LC_ADDRESS        = "de_DE.UTF-8";
      LC_IDENTIFICATION = "de_DE.UTF-8";
      LC_MEASUREMENT    = "de_DE.UTF-8";
      LC_MONETARY       = "de_DE.UTF-8";
      LC_NAME           = "de_DE.UTF-8";
      LC_NUMERIC        = "de_DE.UTF-8";
      LC_PAPER          = "de_DE.UTF-8";
      LC_TELEPHONE      = "de_DE.UTF-8";
      LC_TIME           = "de_DE.UTF-8";
      LC_CTYPE          = "en_US.UTF-8";   # Kompatibilität (XOpenIM etc.)
    };

    # ==========================================
    # TASTATUR (Deutsch — überschreibt base "us")
    # ==========================================
    console.keyMap               = lib.mkDefault "de";
    services.xserver.xkb.layout  = lib.mkDefault "de";
    services.xserver.xkb.variant = lib.mkDefault "";

    # ==========================================
    # ZRAM AKTIVIERUNG / RAM KOMPREMIERUNG
    # ==========================================

    mySystem.zramSwap = {
        enable = lib.mkDefault true;
        algorithm = lib.mkDefault "zstd";    # Der Standard, guter Kompromiss ggfs auf lz4 wechseln
        memoryPercent = lib.mkDefault 50;    # Maximal 50% des RAMs für zram
        priority = lib.mkDefault 100;        # Höher als die SSD-Swap-Priorität (z.B. -1)
    };

    # ==========================================
    # PERSÖNLICHE PAKETE (mergt mit base)
    # ==========================================
    environment.systemPackages = with pkgs; [
      btop-rocm
      keepassxc
      samba
      cifs-utils

      # Messenger APPs
      unstable.whatsapp-electron
      unstable.signal-desktop
    ];

    # ==========================================
    # PERSÖNLICHE ALIASE (mergt mit base)
    # ==========================================
    environment.shellAliases = {
      q = "exit";

      dedupe-home     = "nix-shell -p duperemove --run 'duperemove -r -d -b 1M --hashfile=$HOME/.duperemove.hash $HOME'";
      dedupe-home-dry = "nix-shell -p duperemove --run 'duperemove -r -b 1M --hashfile=$HOME/.duperemove.hash $HOME'";
      dedupe-nix-store = "nix --extra-experimental-features nix-command store optimise";
      wallet-xmr      = "nix-shell -p monero-gui --run monero-wallet-gui";
    };

    # ==========================================
    # PERSÖNLICHE SYSTEM-EINSTELLUNGEN
    # ==========================================
    systemd.tmpfiles.rules = lib.mkDefault [
      "d /home/luisek03/.config/nixpkgs 0755 luisek03 users -"
      "f+ /home/luisek03/.config/nixpkgs/config.nix 0644 luisek03 users - { allowUnfree = true; }"
    ];

    programs.firefox.enable    = lib.mkDefault true;
    programs.kdeconnect.enable = lib.mkDefault true;

    # Hinweis: global allowUnfree macht den allowUnfreePredicate in
    # games/common.nix wirkungslos — später entscheiden: entweder/oder.
    nixpkgs.config.allowUnfree = lib.mkDefault true;
  };
}
